"""Tests for user-supplied reference URL fetch (SSRF guards, parsing)."""

from __future__ import annotations

import pytest

from app.config import get_settings
from app.services.reference_urls import (
    assert_url_safe_for_ssrf,
    fetch_one_reference_url,
    ingest_reference_urls,
    normalize_reference_urls,
    validate_reference_urls_for_request,
)


def _clear_settings_cache() -> None:
    get_settings.cache_clear()


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _clear_settings_cache()
    return get_settings()


def test_normalize_dedupes_and_trims() -> None:
    assert normalize_reference_urls(["  a ", "", "a", "b"]) == ["a", "b"]


def test_validate_rejects_count_and_scheme(settings) -> None:
    urls = [f"https://example.com/{i}" for i in range(settings.reference_url_max_per_request + 1)]
    out, err = validate_reference_urls_for_request(urls, max_count=settings.reference_url_max_per_request)
    assert out is None and err and "At most" in err

    bad, err2 = validate_reference_urls_for_request(["ftp://x/y"], max_count=20)
    assert bad is None and err2 and "scheme" in err2.lower()


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://[::1]/",
        "http://192.168.1.1/",
    ],
)
def test_ssrf_blocks_literal_ips(url: str) -> None:
    ok, reason = assert_url_safe_for_ssrf(url)
    assert ok is False
    assert reason


@pytest.mark.asyncio
async def test_fetch_short_circuits_on_ssrf(settings, monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[bool] = []

    async def _no_fetch(*args, **kwargs):
        called.append(True)
        raise AssertionError("should not fetch blocked URL")

    monkeypatch.setattr("app.services.reference_urls._fetch_body_capped", _no_fetch)
    doc = await fetch_one_reference_url("http://127.0.0.1/secret", settings)
    assert not called
    assert doc.error
    assert "blocked" in (doc.error or "").lower()


@pytest.mark.asyncio
async def test_fetch_html_to_text(settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.reference_urls.assert_url_safe_for_ssrf",
        lambda _u: (True, ""),
    )

    async def _fake_fetch(client, url, max_bytes):  # noqa: ANN001
        return (
            200,
            {"content-type": "text/html; charset=utf-8"},
            b"<html><body><p>Acme Corp headquarters</p></body></html>",
        )

    monkeypatch.setattr("app.services.reference_urls._fetch_body_capped", _fake_fetch)
    doc = await fetch_one_reference_url("https://example.com/about", settings)
    assert doc.kind == "other"
    assert "Acme Corp" in doc.text
    assert "example.com/about" in doc.filename


@pytest.mark.asyncio
async def test_fetch_pdf_bytes(settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.reference_urls.assert_url_safe_for_ssrf",
        lambda _u: (True, ""),
    )
    pdf_blob = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n" + b"x" * 80

    async def _fake_fetch(client, url, max_bytes):  # noqa: ANN001
        return 200, {"content-type": "application/pdf"}, pdf_blob

    monkeypatch.setattr("app.services.reference_urls._fetch_body_capped", _fake_fetch)
    doc = await fetch_one_reference_url("https://example.com/a.pdf", settings)
    assert doc.kind == "pdf"
    assert doc.media_type == "application/pdf"


@pytest.mark.asyncio
async def test_ingest_preserves_order(settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "app.services.reference_urls.assert_url_safe_for_ssrf",
        lambda _u: (True, ""),
    )
    seq: list[str] = []

    async def _fake_fetch(client, url, max_bytes):  # noqa: ANN001
        seq.append(url)
        return 200, {"content-type": "text/plain"}, f"body-{url}".encode()

    monkeypatch.setattr("app.services.reference_urls._fetch_body_capped", _fake_fetch)
    urls = ["https://a.example/1", "https://b.example/2"]
    docs = await ingest_reference_urls(urls, settings)
    assert seq == urls
    assert len(docs) == 2
    assert "body-https://a.example/1" in docs[0].text


@pytest.mark.asyncio
async def test_pipeline_merges_upload_and_url_docs(monkeypatch: pytest.MonkeyPatch) -> None:
    """``run_pipeline`` should pass upload-derived docs plus URL-derived docs into validation."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _clear_settings_cache()

    from app.services import pipeline as pipeline_mod
    from app.services.answer_section import AnsweredQuestion
    from app.services.documents import ParsedDocument
    from app.services.validate_section import ValidationResult

    upload_doc = ParsedDocument(
        "local.pdf",
        "pdf",
        raw_bytes=b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n" + b"z" * 40,
        media_type="application/pdf",
        text="local only",
    )
    url_doc = ParsedDocument(
        "https://example.com/x",
        "other",
        raw_bytes=b"",
        text="from url",
    )

    async def fake_parse(_uploads):  # noqa: ANN202
        return [upload_doc]

    async def fake_ingest(_urls, _settings):  # noqa: ANN202
        return [url_doc]

    captured: dict[str, list] = {}

    async def fake_answer(_company, _section_no, _section_name, questions):  # noqa: ANN202
        return [
            AnsweredQuestion(serial_no=q.serial_no, answer="x", sources=[]) for q in questions
        ]

    async def fake_validate(  # noqa: ANN202
        _company,
        _section_no,
        _section_name,
        questions,
        _answers,
        parsed_docs,
    ):
        captured.setdefault("docs", []).append(parsed_docs)
        return [
            ValidationResult(serial_no=q.serial_no, validation="No", validation_sources=[])
            for q in questions
        ]

    monkeypatch.setattr(pipeline_mod, "parse_documents", fake_parse)
    monkeypatch.setattr(pipeline_mod, "ingest_reference_urls", fake_ingest)
    monkeypatch.setattr(pipeline_mod, "answer_section", fake_answer)
    monkeypatch.setattr(pipeline_mod, "validate_section", fake_validate)

    rows = await pipeline_mod.run_pipeline("Co", [], reference_urls=["https://example.com/x"])
    assert len(rows) == 64
    assert captured["docs"]
    for batch in captured["docs"]:
        names = {d.filename for d in batch}
        assert "local.pdf" in names
        assert "https://example.com/x" in names
