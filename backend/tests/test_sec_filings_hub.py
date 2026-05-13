"""Unit tests for SEC EDGAR hub resolution used to enrich answer citations."""

from __future__ import annotations

from app.services.answer_section import AnsweredQuestion
from app.services.sec_filings_hub import (
    SecFilingsHub,
    _archives_primary_url,
    _pick_best_ticker_match,
    _recent_verification_filings,
    inject_sec_hub_into_answers,
)


def test_pick_best_ticker_match_apple() -> None:
    blob = {
        "0": {"cik_str": 320193, "ticker": "AAPL", "title": "Apple Inc."},
        "1": {"cik_str": 764478, "ticker": "BBY", "title": "BEST BUY CO INC"},
    }
    hit = _pick_best_ticker_match("Apple", blob)
    assert hit is not None
    cik_pad, title = hit
    assert cik_pad == "0000320193"
    assert title == "Apple Inc."


def test_pick_best_ticker_match_ambiguous_returns_none() -> None:
    blob = {
        "0": {"cik_str": 1, "ticker": "X", "title": "ACME CORPORATION"},
        "1": {"cik_str": 2, "ticker": "Y", "title": "ACME CORPORATION INC"},
    }
    hit = _pick_best_ticker_match("ACME CO", blob)
    assert hit is None


def test_archives_primary_url() -> None:
    u = _archives_primary_url("764478", "0001104659-21-058285", "bby-20210130.htm")
    assert u.endswith("/764478/000110465921058285/bby-20210130.htm")


def test_recent_verification_filings_order_and_cap() -> None:
    payload = {
        "filings": {
            "recent": {
                "form": ["10-Q", "10-K/A", "8-K", "10-K", "4"],
                "accessionNumber": [
                    "a1",
                    "a2",
                    "a3",
                    "a4",
                    "a5",
                ],
                "filingDate": [
                    "2025-06-01",
                    "2024-06-09",
                    "2025-06-03",
                    "2025-06-03",
                    "2025-06-03",
                ],
                "primaryDocument": [
                    "q.htm",
                    "k-amend.htm",
                    "e.htm",
                    "annual.htm",
                    "x.htm",
                ],
            }
        }
    }
    out = _recent_verification_filings(payload, "0000764478")
    assert len(out) == 3
    assert out[0]["title"].startswith("SEC filing: 10-K")
    assert "q.htm" in out[1]["url"]
    assert "e.htm" in out[2]["url"]


def test_inject_skips_sentinels() -> None:
    hub = SecFilingsHub(
        cik_pad="0000764478",
        matched_title="Test Co",
        hub_sources=[
            {"title": "Browse", "url": "https://www.sec.gov/edgar/browse/?CIK=0000764478"}
        ],
    )
    rows = [
        [
            AnsweredQuestion(1, "hello", [{"title": "x", "url": "https://a.example/z"}]),
            AnsweredQuestion(2, "Not found", []),
            AnsweredQuestion(3, "Not relevant", []),
        ]
    ]
    inject_sec_hub_into_answers(rows, hub)
    assert rows[0][0].sources[0]["url"] == hub.hub_sources[0]["url"]
    assert rows[0][1].sources == []
    assert rows[0][2].sources == []
