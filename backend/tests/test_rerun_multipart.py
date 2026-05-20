"""Tests for multipart ``POST /api/process/rerun``."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

import app.routes.process as process_mod
from app.config import get_settings
from app.questions import KYC_QUESTIONS
from app.schemas import AttachedDocument, KYCRow
from app.services.pipeline import RunPipelineOutcome


def _clear_settings_cache() -> None:
    get_settings.cache_clear()


def _minimal_rows() -> list[KYCRow]:
    return [
        KYCRow(
            section_no=q.section_no,
            section_name=q.section_name,
            serial_no=q.serial_no,
            question=q.question,
        )
        for q in KYC_QUESTIONS
    ]


class FakeSession:
    async def commit(self) -> None:
        pass


class _SessionCM:
    async def __aenter__(self):
        return FakeSession()

    async def __aexit__(self, *exc: object):
        return None


class _FakeSessionMaker:
    def __call__(self):
        return _SessionCM()


@pytest.fixture
def rerun_client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-rerun-key")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    _clear_settings_cache()

    @dataclass
    class FakeSettings:
        gemini_api_key: str = "test-rerun-key"
        reference_url_max_per_request: int = 20

        def blob_ready(self) -> bool:
            return True

    monkeypatch.setattr(process_mod, "get_settings", lambda: FakeSettings())
    monkeypatch.setattr(process_mod, "db_session_maker", lambda: _FakeSessionMaker())

    from app.main import app

    with TestClient(app) as client:
        yield client


@pytest.fixture
def submission_id() -> uuid.UUID:
    return uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


@pytest.fixture
def stub_submission_record(submission_id: uuid.UUID):
    class Rec:
        id = submission_id
        company_name = "Acme Corp"
        document_filenames = [
            {
                "filename": "keep.pdf",
                "objectKey": "submissions/x/keep.pdf",
                "contentType": "application/pdf",
            }
        ]
        reference_urls: list[str] = []

    return Rec()


def test_rerun_rejects_retain_key_not_in_submission(
    rerun_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    submission_id: uuid.UUID,
    stub_submission_record,
) -> None:
    async def fake_get(_session, _uid):
        return stub_submission_record

    monkeypatch.setattr(process_mod, "get_kyc_submission", fake_get)

    res = rerun_client.post(
        "/api/process/rerun",
        data={
            "submission_id": str(submission_id),
            "retain_object_keys": "s3://evil/unrelated",
            "reference_urls": "https://example.com",
        },
    )
    assert res.status_code == 400
    body = res.json()
    assert "detail" in body
    assert "Invalid retain_object_keys" in str(body["detail"])


def test_rerun_multipart_happy_path_passes_urls_and_uploads(
    rerun_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    submission_id: uuid.UUID,
    stub_submission_record,
) -> None:
    async def fake_get(_session, _uid):
        return stub_submission_record

    monkeypatch.setattr(process_mod, "get_kyc_submission", fake_get)

    captured: dict[str, object] = {}

    async def fake_get_bytes(_settings, key: str):
        captured["fetched_key"] = key
        return b"%PDF-1.4 test"

    async def fake_upload(_settings, _sid, uploads):
        captured["upload_tuples"] = uploads
        return [
            AttachedDocument(
                filename=t[0],
                object_key=f"new/{i}",
                size_bytes=len(t[1]),
                content_type=t[2],
            )
            for i, t in enumerate(uploads)
        ]

    async def fake_pipeline(company: str, uploads, reference_urls=None, **kwargs):
        captured["company"] = company
        captured["pipeline_uploads"] = uploads
        captured["pipeline_urls"] = list(reference_urls or [])
        return RunPipelineOutcome(rows=_minimal_rows(), section_errors=[])

    class FakeSaved:
        def __init__(self) -> None:
            self.id = uuid.uuid4()
            self.created_at = datetime.now(timezone.utc)

    async def fake_create(_session, **kwargs):
        captured["saved_ref_urls"] = kwargs.get("reference_urls")
        return FakeSaved()

    monkeypatch.setattr(process_mod, "get_object_bytes", fake_get_bytes)
    monkeypatch.setattr(process_mod, "upload_submission_files", fake_upload)
    monkeypatch.setattr(process_mod, "run_pipeline", fake_pipeline)
    monkeypatch.setattr(process_mod, "create_kyc_submission", fake_create)

    url = "https://example.com/page"
    res = rerun_client.post(
        "/api/process/rerun",
        data={
            "submission_id": str(submission_id),
            "retain_object_keys": "submissions/x/keep.pdf",
            "reference_urls": url,
        },
    )
    assert res.status_code == 200, res.text
    assert captured["fetched_key"] == "submissions/x/keep.pdf"
    assert captured["company"] == "Acme Corp"
    assert captured["pipeline_urls"] == [url]
    pts = captured["pipeline_uploads"]
    assert isinstance(pts, list) and len(pts) == 1
    assert pts[0] == ("keep.pdf", b"%PDF-1.4 test", "application/pdf")
    assert captured["saved_ref_urls"] == [url]
