"""S3-compatible object storage (upload + presigned downloads)."""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import PurePosixPath
from uuid import UUID

import boto3
from botocore.config import Config

from app.config import Settings
from app.schemas import AttachedDocument

logger = logging.getLogger(__name__)

_SAFE_NAME_RE = re.compile(r"[^\w.\-() ]+")


def _s3_client(settings: Settings):
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
        ),
    )


def _sanitize_original_filename(name: str) -> str:
    base = PurePosixPath(name).name
    if not base or base in {".", ".."}:
        base = "document"
    base = base.replace("\x00", "").strip()
    base = _SAFE_NAME_RE.sub("_", base)[:200]
    return base or "document"


def submission_object_prefix(submission_id: UUID) -> str:
    """All objects for a submission live under this prefix (no trailing slash in return)."""
    return f"kyc/{submission_id}"


def build_upload_key(submission_id: UUID, index: int, original_filename: str) -> str:
    safe = _sanitize_original_filename(original_filename)
    return f"{submission_object_prefix(submission_id)}/{index:02d}_{safe}"


async def upload_submission_files(
    settings: Settings,
    submission_id: UUID,
    uploads: list[tuple[str, bytes, str]],
) -> list[AttachedDocument]:
    """Upload each attachment; returns metadata including ``objectKey`` for downloads."""
    assert settings.s3_bucket
    client = _s3_client(settings)
    out: list[AttachedDocument] = []

    for i, (filename, body, content_type) in enumerate(uploads):
        key = build_upload_key(submission_id, i, filename)

        def _put() -> None:
            kwargs: dict = {
                "Bucket": settings.s3_bucket,
                "Key": key,
                "Body": body,
            }
            if content_type:
                kwargs["ContentType"] = content_type
            client.put_object(**kwargs)

        await asyncio.to_thread(_put)
        ct = content_type or "application/octet-stream"
        logger.info(
            "Stored upload in bucket %s key=%s (~%.2f KiB)",
            settings.s3_bucket,
            key,
            len(body) / 1024,
        )
        out.append(
            AttachedDocument(
                filename=_sanitize_original_filename(filename),
                size_bytes=len(body),
                content_type=ct,
                object_key=key,
            )
        )

    return out


def presigned_download_url(
    settings: Settings,
    *,
    object_key: str,
    filename: str,
    expires_seconds: int = 3600,
) -> str:
    """Return a time-limited HTTPS URL (GET) for browser download."""
    assert settings.s3_bucket
    safe_disp = filename.replace('"', "'").encode("ascii", "replace").decode("ascii") or "download"
    disposition = f'attachment; filename="{safe_disp}"'

    client = _s3_client(settings)
    return client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.s3_bucket,
            "Key": object_key,
            "ResponseContentDisposition": disposition,
        },
        ExpiresIn=expires_seconds,
    )


def key_belongs_to_submission(object_key: str, submission_id: UUID) -> bool:
    prefix = submission_object_prefix(submission_id) + "/"
    return object_key.startswith(prefix) and ".." not in object_key
