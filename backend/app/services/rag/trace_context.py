"""Thread-local RAG trace collector for the active pipeline run."""

from __future__ import annotations

from contextvars import ContextVar, Token

from app.services.rag.observability import RagTraceCollector

_collector: ContextVar[RagTraceCollector | None] = ContextVar(
    "rag_trace_collector",
    default=None,
)


def get_collector() -> RagTraceCollector | None:
    return _collector.get()


def set_collector(collector: RagTraceCollector | None) -> Token:
    return _collector.set(collector)


def reset_collector(token: Token) -> None:
    _collector.reset(token)
