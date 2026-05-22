"""Tests for answer source prioritisation (SEC hub first) and per-row caps."""

from __future__ import annotations

from unittest.mock import MagicMock

from app.config import ANSWER_SOURCES_DOMAIN_PRIORITY_SUFFIXES
from app.services.source_urls import prioritize_and_cap_answer_sources

#test
def _settings(max_count: int = 3):
    return MagicMock(
        answer_sources_max_count=max_count,
        answer_sources_domain_priority_suffixes=ANSWER_SOURCES_DOMAIN_PRIORITY_SUFFIXES,
    )


def test_sec_hub_ordered_first_then_others_under_cap() -> None:
    hub = [
        {"title": "Browse", "url": "https://www.sec.gov/edgar/browse/?CIK=0000764478"},
        {"title": "10-Q", "url": "https://www.sec.gov/Archives/edgar/data/764478/acc/q.htm"},
    ]
    aq = MagicMock()
    aq.sources = [
        {"title": "news", "url": "https://news.example/item"},
        {
            "title": "Browse",
            "url": "https://www.sec.gov/edgar/browse/?CIK=0000764478",
        },
        {"title": "10-Q filing", "url": hub[1]["url"]},
        {"title": "extra", "url": "https://other.example/z"},
        {
            "title": "dup browse",
            "url": "https://www.sec.gov/edgar/browse/?CIK=0000764478",
        },
    ]
    sections = [[aq]]
    prioritize_and_cap_answer_sources(sections, _settings(3), verification_hub_sources=hub)
    out = aq.sources
    assert len(out) == 3
    assert "sec.gov/edgar/browse" in out[0]["url"]
    assert "Archives/edgar/data" in out[1]["url"]
    assert out[2]["url"] == "https://news.example/item"


def test_without_hub_truncates_original_order() -> None:
    aq = MagicMock()
    aq.sources = [
        {"title": "a", "url": "https://a.example/1"},
        {"title": "b", "url": "https://b.example/2"},
        {"title": "c", "url": "https://c.example/3"},
        {"title": "d", "url": "https://d.example/4"},
    ]
    prioritize_and_cap_answer_sources([[aq]], _settings(2), verification_hub_sources=None)
    assert len(aq.sources) == 2
    assert aq.sources[0]["url"] == "https://a.example/1"


def test_priority_suffix_hosts_before_generic_when_no_hub_overlap() -> None:
    aq = MagicMock()
    aq.sources = [
        {"title": "news", "url": "https://news.example/item"},
        {"title": "CH", "url": "https://find-and-update.company-information.service.gov.uk/company/123"},
        {"title": "blog", "url": "https://blog.example/x"},
    ]
    prioritize_and_cap_answer_sources([[aq]], _settings(2), verification_hub_sources=None)
    assert len(aq.sources) == 2
    assert "company-information.service.gov.uk" in aq.sources[0]["url"]
    assert aq.sources[1]["url"] == "https://news.example/item"


def test_hub_slot_skipped_when_url_missing_from_answer_sources() -> None:
    hub = [
        {"title": "Browse", "url": "https://www.sec.gov/edgar/browse/?CIK=999"},
        {"title": "Filing", "url": "https://www.sec.gov/Archives/edgar/data/1/acc/x.htm"},
    ]
    aq = MagicMock()
    aq.sources = [{"title": "only", "url": "https://only.example/o"}]
    prioritize_and_cap_answer_sources([[aq]], _settings(3), verification_hub_sources=hub)
    assert aq.sources == [{"title": "only", "url": "https://only.example/o"}]
