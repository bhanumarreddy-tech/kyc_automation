"""Index parsed documents into pgvector for a submission."""

from __future__ import annotations

import logging
import time
import uuid

from sqlalchemy import delete, func, select, text

from app.config import Settings, get_settings
from app.db.models import KYCDocumentChunk
from app.db.session import db_session_maker
from app.db.submissions import ensure_submission_stub
from app.services.documents import ParsedDocument
from app.services.rag.chunking import chunk_parsed_documents, document_stable_id
from app.services.rag.contextualize import contextualize_chunks
from app.services.rag.embeddings import embed_texts

logger = logging.getLogger(__name__)


def rag_indexing_available(settings: Settings | None = None) -> bool:
    s = settings or get_settings()
    return bool(s.database_url and s.rag_enabled and s.gemini_api_key)


async def index_submission_documents(
    submission_id: uuid.UUID,
    company: str,
    documents: list[ParsedDocument],
    *,
    settings: Settings | None = None,
) -> int:
    """Chunk, contextualize, embed, and store chunks. Returns chunk count."""
    s = settings or get_settings()
    started = time.perf_counter()
    if not rag_indexing_available(s):
        from app.services.mlflow_tracing import log_indexing

        log_indexing(
            chunk_count=0,
            document_count=0,
            duration_ms=0,
            skipped=True,
            skip_reason="rag_unavailable",
        )
        return 0

    started = time.perf_counter()
    maker = db_session_maker()
    if maker is None:
        from app.services.mlflow_tracing import log_indexing

        log_indexing(
            chunk_count=0,
            document_count=0,
            duration_ms=0,
            skipped=True,
            skip_reason="database_unavailable",
        )
        return 0

    text_docs = [
        d
        for d in documents
        if (d.text or "").strip() and not d.error
    ]
    if not text_docs:
        from app.services.mlflow_tracing import log_indexing

        log_indexing(
            chunk_count=0,
            document_count=0,
            duration_ms=int((time.perf_counter() - started) * 1000),
            skipped=True,
            skip_reason="no_text_documents",
        )
        return 0

    drafts = chunk_parsed_documents(
        text_docs,
        target_chars=s.rag_chunk_target_chars,
        overlap_chars=s.rag_chunk_overlap_chars,
        small_doc_full_text_chars=s.rag_small_doc_full_text_chars,
    )
    if not drafts:
        from app.services.mlflow_tracing import log_indexing

        log_indexing(
            chunk_count=0,
            document_count=len(text_docs),
            duration_ms=int((time.perf_counter() - started) * 1000),
            skipped=True,
            skip_reason="no_chunks_produced",
        )
        return 0

    contextualized = await contextualize_chunks(company, drafts, s)
    vectors = await embed_texts(contextualized, s, task_type="RETRIEVAL_DOCUMENT")
    if len(vectors) != len(drafts):
        logger.warning(
            "Embedding count mismatch: drafts=%d vectors=%d",
            len(drafts),
            len(vectors),
        )
        n = min(len(vectors), len(drafts))
        drafts = drafts[:n]
        contextualized = contextualized[:n]
        vectors = vectors[:n]

    async with maker() as session:
        await ensure_submission_stub(
            session,
            submission_id=submission_id,
            company_name=company,
        )
        await session.execute(
            delete(KYCDocumentChunk).where(
                KYCDocumentChunk.submission_id == submission_id
            )
        )
        rows: list[KYCDocumentChunk] = []
        for draft, ctx_text, vec in zip(drafts, contextualized, vectors, strict=False):
            meta = dict(draft.metadata)
            meta["document_id"] = draft.document_id
            rows.append(
                KYCDocumentChunk(
                    id=uuid.uuid4(),
                    submission_id=submission_id,
                    document_id=draft.document_id,
                    chunk_index=draft.chunk_index,
                    page_start=draft.page_start,
                    page_end=draft.page_end,
                    content=draft.content,
                    contextualized_content=ctx_text,
                    embedding=vec,
                    chunk_metadata=meta,
                )
            )
        session.add_all(rows)
        await session.flush()
        # Populate tsvector for hybrid lexical search
        await session.execute(
            text(
                """
                UPDATE kyc_document_chunks
                SET content_tsv = to_tsvector('english', contextualized_content)
                WHERE submission_id = :sid
                """
            ),
            {"sid": submission_id},
        )
        await session.commit()

    logger.info(
        "RAG indexed submission=%s: %d chunk(s) from %d document(s)",
        submission_id,
        len(rows),
        len({document_stable_id(d) for d in text_docs}),
    )
    from app.services.mlflow_tracing import log_indexing

    log_indexing(
        chunk_count=len(rows),
        document_count=len({document_stable_id(d) for d in text_docs}),
        duration_ms=int((time.perf_counter() - started) * 1000),
    )
    return len(rows)


async def count_submission_chunks(submission_id: uuid.UUID) -> int:
    maker = db_session_maker()
    if maker is None:
        return 0
    async with maker() as session:
        result = await session.execute(
            select(func.count())
            .select_from(KYCDocumentChunk)
            .where(KYCDocumentChunk.submission_id == submission_id)
        )
        return int(result.scalar_one() or 0)
