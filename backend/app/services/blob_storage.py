"""Vercel Blob storage (upload + authorized downloads for private stores)."""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import UUID

from vercel.blob import get_async, put_async
from vercel.blob.errors import BlobNotFoundError

from app.config import Settings
from app.schemas import AttachedDocument

logger = logging.getLogger(__name__)

_SAFE_NAME_RE = re.compile(r"[^\w.\-() ]+")
_BLOB_ACCESS = "private"


def submission_object_prefix(submission_id: UUID) -> str:
    """All objects for a submission live under this prefix (no trailing slash in return)."""
    return f"kyc/{submission_id}"


def build_upload_key(submission_id: UUID, index: int, original_filename: str) -> str:
    safe = _sanitize_original_filename(original_filename)
    return f"{submission_object_prefix(submission_id)}/{index:02d}_{safe}"


def _sanitize_original_filename(name: str) -> str:
    base = PurePosixPath(name).name
    if not base or base in {".", ".."}:
        base = "document"
    base = base.replace("\x00", "").strip()
    base = _SAFE_NAME_RE.sub("_", base)[:200]
    return base or "document"


def _blob_token(settings: Settings) -> str:
    assert settings.blob_read_write_token
    return settings.blob_read_write_token


async def upload_submission_files(
    settings: Settings,
    submission_id: UUID,
    uploads: list[tuple[str, bytes, str]],
) -> list[AttachedDocument]:
    """Upload each attachment; returns metadata including ``objectKey`` (blob pathname)."""
    token = _blob_token(settings)
    out: list[AttachedDocument] = []

    for i, (filename, body, content_type) in enumerate(uploads):
        pathname = build_upload_key(submission_id, i, filename)
        result = await put_async(
            pathname,
            body,
            access=_BLOB_ACCESS,
            content_type=content_type or None,
            token=token,
        )
        ct = content_type or result.content_type or "application/octet-stream"
        logger.info(
            "Stored upload in Vercel Blob pathname=%s (~%.2f KiB)",
            result.pathname,
            len(body) / 1024,
        )
        out.append(
            AttachedDocument(
                filename=_sanitize_original_filename(filename),
                size_bytes=len(body),
                content_type=ct,
                object_key=result.pathname,
            )
        )

    return out


async def get_object_bytes(settings: Settings, object_key: str) -> bytes:
    """Fetch blob body from storage (server-side; used for reruns)."""
    try:
        result = await get_async(
            object_key,
            access=_BLOB_ACCESS,
            token=_blob_token(settings),
        )
    except BlobNotFoundError as exc:
        raise FileNotFoundError(object_key) from exc
    return result.content


@dataclass(frozen=True)
class AttachmentDownload:
    content: bytes
    content_type: str
    content_disposition: str


async def fetch_attachment_download(
    settings: Settings,
    *,
    object_key: str,
    filename: str,
) -> AttachmentDownload:
    """Load blob bytes for an authorized browser download."""
    safe_disp = filename.replace('"', "'").encode("ascii", "replace").decode("ascii") or "download"
    disposition = f'attachment; filename="{safe_disp}"'
    try:
        result = await get_async(
            object_key,
            access=_BLOB_ACCESS,
            token=_blob_token(settings),
        )
    except BlobNotFoundError as exc:
        raise FileNotFoundError(object_key) from exc
    return AttachmentDownload(
        content=result.content,
        content_type=result.content_type or "application/octet-stream",
        content_disposition=disposition,
    )


def key_belongs_to_submission(object_key: str, submission_id: UUID) -> bool:
    prefix = submission_object_prefix(submission_id) + "/"
    return object_key.startswith(prefix) and ".." not in object_key
