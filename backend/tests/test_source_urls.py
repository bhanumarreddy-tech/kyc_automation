"""Tests for Gemini source URL normalization and optional SEC EDGAR repair."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.services.answer_section import AnsweredQuestion
from app.services import source_urls as su


def _settings(**overrides: object) -> Settings:
    base = dict(
        gemini_api_key="k",
        gemini_model="m",
        gemini_validation_model="v",
        source_url_verify_enabled=True,
        source_url_verify_timeout_seconds=15.0,
        source_url_verify_max_urls=250,
        reference_url_max_redirects=5,
        reference_url_fetch_contact="https://example.com; t@example.com",
        reference_url_fetch_user_agent=None,
    )
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("raw", "want_substr"),
    [
        (
            "https://sec-archives.s3.amazonaws.com/edgar/data/73309/000119312512080353/dex33.htm",
            "https://www.sec.gov/Archives/edgar/data/73309/000119312512080353/dex33.htm",
        ),
        (
            "https://sec-archives.s3.us-east-1.amazonaws.com/edgar/data/1/2/a.htm",
            "https://www.sec.gov/Archives/edgar/data/1/2/a.htm",
        ),
        (
            "https://s3.amazonaws.com/sec-archives/edgar/data/9/8/7/x.txt",
            "https://www.sec.gov/Archives/edgar/data/9/8/7/x.txt",
        ),
    ],
)
def test_normalize_sec_edgar_s3_mirrors(raw: str, want_substr: str) -> None:
    assert su.normalize_sec_edgar_source_url(raw) == want_substr


def test_normalize_preserves_existing_archives_www_url() -> None:
    u = "https://www.sec.gov/Archives/edgar/data/73309/000119312512080353/dex33.htm"
    assert su.normalize_sec_edgar_source_url(u) == u


def test_normalize_adds_archives_prefix_on_sec_host() -> None:
    u = "https://www.sec.gov/edgar/data/73309/000119312512080353/dex33.htm"
    assert su.normalize_sec_edgar_source_url(u) == (
        "https://www.sec.gov/Archives/edgar/data/73309/000119312512080353/dex33.htm"
    )


def test_edgar_filing_index_fallback() -> None:
    u = "https://www.sec.gov/Archives/edgar/data/73309/000119312512080353/dex33.htm"
    fb = su.edgar_filing_index_fallback_url(u)
    assert fb == (
        "https://www.sec.gov/Archives/edgar/data/73309/000119312512080353/"
        "000119312512080353-index.htm"
    )


def test_edgar_filing_index_fallback_not_for_s3_host() -> None:
    u = "https://sec-archives.s3.amazonaws.com/edgar/data/1/2/3/a.htm"
    assert su.edgar_filing_index_fallback_url(u) is None


@pytest.mark.asyncio
async def test_verify_repairs_when_exhibit_404_index_ok(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_probe(
        _client: object,
        url: str,
    ) -> tuple[int, bytes]:
        if "dex33" in url:
            return 404, b""
        return 200, b"ok"

    monkeypatch.setattr(su, "_probe_url", fake_probe)
    out = await su.verify_or_repair_source_url(
        "https://www.sec.gov/Archives/edgar/data/73309/000119312512080353/dex33.htm",
        _settings(),
    )
    assert out is not None
    assert out.endswith("000119312512080353-index.htm")


@pytest.mark.asyncio
async def test_verify_prefers_index_when_exhibit_404_and_index_inconclusive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_probe(
        _client: object,
        url: str,
    ) -> tuple[int, bytes]:
        if "dex33" in url:
            return 404, b""
        return 503, b""

    monkeypatch.setattr(su, "_probe_url", fake_probe)
    out = await su.verify_or_repair_source_url(
        "https://www.sec.gov/Archives/edgar/data/73309/000119312512080353/dex33.htm",
        _settings(),
    )
    assert out is not None
    assert out.endswith("000119312512080353-index.htm")


@pytest.mark.asyncio
async def test_verify_drops_when_exhibit_and_index_definitely_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_probe(
        _client: object,
        _url: str,
    ) -> tuple[int, bytes]:
        return 404, b""

    monkeypatch.setattr(su, "_probe_url", fake_probe)
    out = await su.verify_or_repair_source_url(
        "https://www.sec.gov/Archives/edgar/data/73309/000119312512080353/dex33.htm",
        _settings(),
    )
    assert out is None


@pytest.mark.asyncio
async def test_verify_keeps_url_when_probe_inconclusive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_probe(
        _client: object,
        _url: str,
    ) -> tuple[int, bytes]:
        return 503, b""

    monkeypatch.setattr(su, "_probe_url", fake_probe)
    raw = "https://www.sec.gov/Archives/edgar/data/73309/000119312512080353/dex33.htm"
    out = await su.verify_or_repair_source_url(raw, _settings())
    assert out == raw


@pytest.mark.asyncio
async def test_sanitize_normalizes_when_verify_disabled() -> None:
    raw = "https://sec-archives.s3.amazonaws.com/edgar/data/1/2/3/a.htm"
    aq = AnsweredQuestion(
        serial_no=1,
        answer="x",
        sources=[{"title": "t", "url": raw}],
    )
    await su.sanitize_answer_sources_urls(
        [[aq]],
        _settings(source_url_verify_enabled=False),
    )
    assert aq.sources[0]["url"] == (
        "https://www.sec.gov/Archives/edgar/data/1/2/3/a.htm"
    )


@pytest.mark.asyncio
async def test_sanitize_verify_repairs_via_cache(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    n = {"c": 0}

    async def fake_probe(
        _client: object,
        url: str,
    ) -> tuple[int, bytes]:
        n["c"] += 1
        if "missing" in url:
            return 404, b""
        return 200, b""

    monkeypatch.setattr(su, "_probe_url", fake_probe)
    bad = (
        "https://www.sec.gov/Archives/edgar/data/9/000000000009999/missing.htm"
    )
    a1 = AnsweredQuestion(1, "a", [{"title": "t", "url": bad}])
    a2 = AnsweredQuestion(2, "b", [{"title": "t", "url": bad}])
    await su.sanitize_answer_sources_urls([[a1], [a2]], _settings())
    assert a1.sources[0]["url"] == a2.sources[0]["url"]
    assert a1.sources[0]["url"].endswith("-index.htm")
    assert n["c"] == 2
