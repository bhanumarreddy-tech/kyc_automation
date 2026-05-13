"""Expand and shard uploaded documents so validation stays within Gemini file limits."""

from __future__ import annotations

import io
import logging
import re
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from app.config import Settings
from app.services.documents import ParsedDocument, parse_pdf_bytes

logger = logging.getLogger(__name__)

def is_native_validation_part(
    doc: ParsedDocument,
    settings: Settings,
    *,
    attach_natively: bool,
) -> bool:
    """Whether this document is sent as a binary PDF/image part (not extracted text)."""
    if not attach_natively:
        return False
    lim_pdf = settings.validation_max_pdf_bytes
    lim_img = settings.validation_max_image_bytes
    if (
        doc.kind == "pdf"
        and doc.raw_bytes
        and len(doc.raw_bytes) <= lim_pdf
        and not doc.error
    ):
        return True
    return bool(
        doc.kind == "image"
        and doc.raw_bytes
        and len(doc.raw_bytes) <= lim_img
    )


def _stem_ext(filename: str) -> tuple[str, str]:
    p = Path(filename)
    stem, ext = p.stem, p.suffix.lower() or ""
    return stem, ext or ""


def _material_display_base(doc: ParsedDocument) -> str:
    """Prefer full reference URL for labels; else :attr:`ParsedDocument.filename`."""
    u = (doc.extra or {}).get("source_url")
    if isinstance(u, str) and u.strip():
        return u.strip()
    fn = doc.filename
    if isinstance(fn, str) and fn.lower().startswith(("http://", "https://")):
        return fn.strip()
    return doc.filename


def _label_stem_suffix(display_base: str, original_filename: str) -> tuple[str, str]:
    """Path-based stem/suffix breaks on http(s) URLs; keep the full URL as the label stem."""
    if display_base.lower().startswith(("http://", "https://")):
        suf = Path(original_filename).suffix.lower() or ""
        return display_base, suf
    stem, suf = _stem_ext(display_base)
    return stem, suf or ""


def _write_pdf_subset(reader: PdfReader, indices: list[int]) -> bytes:
    writer = PdfWriter()
    for i in indices:
        writer.add_page(reader.pages[i])
    buf = io.BytesIO()
    writer.write(buf)
    return buf.getvalue()


def _split_page_indices_recursive(
    reader: PdfReader,
    indices: list[int],
    base_stem: str,
    suffix: str,
    max_pdf_bytes: int,
) -> list[tuple[str, bytes]]:
    if not indices:
        return []

    blob = _write_pdf_subset(reader, indices)
    first_page = indices[0] + 1
    last_page = indices[-1] + 1
    label_pages = (
        f"{first_page}"
        if first_page == last_page
        else f"{first_page}–{last_page}"
    )
    filename = f"{base_stem} · pages {label_pages}{suffix}"

    if len(blob) <= max_pdf_bytes or len(indices) == 1:
        if len(indices) == 1 and len(blob) > max_pdf_bytes:
            logger.warning(
                "PDF slice %s is %d bytes (exceeds cap %d); sending anyway.",
                filename,
                len(blob),
                max_pdf_bytes,
            )
        return [(filename, blob)]

    mid = len(indices) // 2
    left_idx = indices[:mid]
    right_idx = indices[mid:]
    return (
        _split_page_indices_recursive(
            reader, left_idx, base_stem, suffix, max_pdf_bytes
        )
        + _split_page_indices_recursive(
            reader, right_idx, base_stem, suffix, max_pdf_bytes
        )
    )


def _pdf_slices_for_reader(
    reader: PdfReader,
    display_base: str,
    original_filename: str,
    settings: Settings,
) -> list[tuple[str, bytes]]:
    n = len(reader.pages)
    stem, suf = _label_stem_suffix(display_base, original_filename)
    groups: list[list[int]] = []
    max_pg = settings.validation_max_pages_per_pdf_slice
    for start in range(0, n, max_pg):
        groups.append(list(range(start, min(start + max_pg, n))))

    slices: list[tuple[str, bytes]] = []
    max_b = settings.validation_max_pdf_bytes
    for grp in groups:
        slices.extend(
            _split_page_indices_recursive(reader, grp, stem, suf, max_b)
        )
    return slices


def expand_pdf_document(doc: ParsedDocument, settings: Settings) -> list[ParsedDocument]:
    """Split oversized / long PDFs into API-safe slices."""

    if doc.kind != "pdf" or not doc.raw_bytes:
        return [doc]

    page_count = doc.pages or 0
    oversized_pages = (
        page_count > 0
        and page_count > settings.validation_max_pages_per_pdf_slice
    )
    oversized_bytes = len(doc.raw_bytes) > settings.validation_max_pdf_bytes
    if not oversized_pages and not oversized_bytes and not doc.error:
        return [doc]

    if doc.error:
        logger.warning(
            "PDF %s marked parse-error; emitting single slice unchanged.",
            doc.filename,
        )
        return [doc]

    try:
        reader = PdfReader(io.BytesIO(doc.raw_bytes))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Cannot split PDF %s: %s", doc.filename, exc)
        return [doc]

    pairs = _pdf_slices_for_reader(
        reader,
        _material_display_base(doc),
        doc.filename,
        settings,
    )
    parsed: list[ParsedDocument] = []
    for name, blob in pairs:
        sub = parse_pdf_bytes(name, blob)
        su = (doc.extra or {}).get("source_url")
        if isinstance(su, str) and su.strip():
            sub.extra = {**sub.extra, "source_url": su.strip()}
        parsed.append(sub)
    return parsed or [doc]


def expand_all_documents(
    docs: list[ParsedDocument],
    settings: Settings,
) -> list[ParsedDocument]:
    out: list[ParsedDocument] = []
    for d in docs:
        out.extend(expand_pdf_document(d, settings))
    return out


def _chunk_plain_text(doc: ParsedDocument, chunk_chars: int) -> list[str]:
    if not doc.text or len(doc.text) <= chunk_chars:
        return [doc.text] if doc.text else []

    slices: list[str] = []
    pos = 0
    ln = len(doc.text)
    while pos < ln:
        slices.append(doc.text[pos : pos + chunk_chars])
        pos += chunk_chars
    return slices


def expand_large_text_documents(
    docs: list[ParsedDocument],
    settings: Settings,
    *,
    attach_natively: bool,
) -> list[ParsedDocument]:
    """Split bulky extracted-text documents so each row fits later shard budgets."""
    cc = settings.validation_text_chunk_chars
    out: list[ParsedDocument] = []
    for doc in docs:
        if not (doc.text and doc.text.strip()):
            out.append(doc)
            continue
        if is_native_validation_part(doc, settings, attach_natively=attach_natively):
            out.append(doc)
            continue

        chunks = _chunk_plain_text(doc, cc)
        if len(chunks) <= 1:
            out.append(doc)
            continue

        base = _material_display_base(doc)
        if base.lower().startswith(("http://", "https://")):
            logical_base = base
        else:
            stem, suf = _stem_ext(doc.filename)
            logical_base = stem + suf
        total = len(chunks)
        for idx, txt in enumerate(chunks, start=1):
            chunk_extra = {**(doc.extra or {}), "orig_filename": logical_base}
            out.append(
                ParsedDocument(
                    filename=f"{logical_base} · text part {idx}/{total}",
                    kind="other",
                    raw_bytes=b"",
                    media_type="",
                    text=txt,
                    pages=None,
                    extra=chunk_extra,
                )
            )

    return out


def estimated_text_budget(
    docs: list[ParsedDocument],
    settings: Settings,
    *,
    attach_natively: bool,
) -> int:
    total = 0
    for d in docs:
        if is_native_validation_part(d, settings, attach_natively=attach_natively):
            continue
        total += len(d.text) if d.text else 0
    return total


def page_aware_text_chunks(doc: ParsedDocument, target_chars: int) -> list[str]:
    """Prefer grouping on PDF ``[Page N]`` blocks, capped at ``target_chars``."""
    txt = doc.text.strip()
    if not txt:
        return []
    if len(txt) <= target_chars:
        return [txt]
    segments = [
        p.strip() for p in re.split(r"(?=\[Page \d+\])", txt) if p.strip()
    ]
    if not segments:
        return _chunk_plain_text(doc, target_chars)

    merged: list[str] = []
    buf = ""
    for seg in segments:
        cand = seg if not buf else f"{buf}\n\n{seg}".strip()
        if len(cand) <= target_chars:
            buf = cand
            continue
        if buf:
            merged.append(buf)
            buf = ""
        if len(seg) <= target_chars:
            buf = seg
            continue
        merged.extend(
            _chunk_plain_text(
                ParsedDocument(doc.filename, "other", b"", text=seg),
                target_chars,
            )
        )
    if buf:
        merged.append(buf)

    normalized: list[str] = []
    for m in merged:
        if len(m) <= target_chars:
            normalized.append(m)
        else:
            normalized.extend(
                _chunk_plain_text(
                    ParsedDocument(doc.filename, "other", b"", text=m),
                    target_chars,
                )
            )

    return normalized if normalized else _chunk_plain_text(doc, target_chars)


def retrieval_selected_documents(
    text_docs: list[ParsedDocument],
    query_text: str,
    settings: Settings,
    *,
    top_k: int,
) -> list[ParsedDocument]:
    """Cheap keyword-overlap retrieval: pick up to ``top_k`` chunks under budget."""
    qt = query_text.lower()
    query_words = {w for w in re.findall(r"[a-z0-9]{3,}", qt)}

    chunks: list[tuple[float, str, str]] = []
    for doc in text_docs:
        if not doc.text or not doc.text.strip():
            continue
        labeled = []
        tc = settings.validation_retrieval_chunk_target_chars
        for ci, ck in enumerate(page_aware_text_chunks(doc, tc), start=1):
            lbl = f"{doc.filename} · retrieved chunk {ci}"
            labeled.append((lbl, ck))
        score_base = sum(doc.text.lower().count(w) for w in query_words)

        for lbl, ck in labeled:
            cl = ck.lower()
            overlap = (
                score_base / max(16, len(ck.split()))
                + sum(cl.count(w) for w in query_words)
            )
            chunks.append((float(overlap), lbl, ck))

    chunks.sort(key=lambda t: (-t[0], t[1]))
    selected: list[ParsedDocument] = []
    remaining = settings.validation_max_total_text_chars - 8_000
    for _, lbl, ck in chunks:
        if len(selected) >= top_k:
            break
        if len(ck) + 64 > remaining:
            continue
        selected.append(
            ParsedDocument(
                filename=lbl,
                kind="other",
                raw_bytes=b"",
                text=ck,
                extra=dict(doc.extra or {}),
            )
        )
        remaining -= len(ck) + 64

    return selected


def pack_validation_shards(
    docs: list[ParsedDocument],
    settings: Settings,
    *,
    attach_natively: bool,
) -> list[list[ParsedDocument]]:
    """Greedy-pack documents into Gemini-sized validation requests."""

    max_parts = settings.validation_max_native_parts_per_request
    max_text = settings.validation_max_total_text_chars
    shards: list[list[ParsedDocument]] = []
    cur: list[ParsedDocument] = []
    text_used = 0
    native_parts = 0

    def flush() -> None:
        nonlocal cur, text_used, native_parts
        if cur:
            shards.append(cur)
        cur = []
        text_used = 0
        native_parts = 0

    for doc in docs:
        native = is_native_validation_part(
            doc, settings, attach_natively=attach_natively
        )
        cost = 0 if native else len(doc.text or "")

        if native and native_parts >= max_parts:
            flush()
        elif (
            cur
            and not native
            and cost > 0
            and text_used + cost > max_text
        ):
            flush()

        cur.append(doc)
        if is_native_validation_part(doc, settings, attach_natively=attach_natively):
            native_parts += 1
        else:
            text_used += cost

    flush()

    if not shards and docs:
        return [docs[:]]
    max_api_files = 3_000
    if shards and (
        settings.validation_max_native_parts_per_request * len(shards) > max_api_files
        or sum(len(v) for v in shards) > max_api_files
    ):
        logger.warning(
            "Validation shard count/size may exceed API file ceilings; tighten limits."
        )
    return shards
