"""In-memory pipeline job registry for async processing + cancellation (single-process)."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


@dataclass
class PipelineJobState:
    job_id: str
    status: JobStatus = "queued"
    phase: str = ""
    detail: str = ""
    answer_completed: int = 0
    answer_total: int = 8
    validate_completed: int = 0
    validate_total: int = 64
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task | None = None
    result_payload: dict[str, Any] | None = None
    error_message: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def snapshot(self) -> dict[str, Any]:
        return {
            "jobId": self.job_id,
            "status": self.status,
            "phase": self.phase,
            "detail": self.detail,
            "answerCompleted": self.answer_completed,
            "answerTotal": self.answer_total,
            "validateCompleted": self.validate_completed,
            "validateTotal": self.validate_total,
        }


_jobs: dict[str, PipelineJobState] = {}
_jobs_lock = asyncio.Lock()


def register_job() -> PipelineJobState:
    job_id = uuid.uuid4().hex
    st = PipelineJobState(job_id=job_id)
    _jobs[job_id] = st
    return st


async def get_job(job_id: str) -> PipelineJobState | None:
    async with _jobs_lock:
        return _jobs.get(job_id)


def pop_job(job_id: str) -> None:
    _jobs.pop(job_id, None)


async def request_cancel(job_id: str) -> bool:
    async with _jobs_lock:
        st = _jobs.get(job_id)
        if st is None:
            return False
        st.cancel_event.set()
        st.phase = "cancelling"
        st.detail = "Cancellation requested — will stop after the current pipeline phase"
        return True


async def update_job(job_id: str, **fields: Any) -> None:
    async with _jobs_lock:
        st = _jobs.get(job_id)
        if st is None:
            return
        for k, v in fields.items():
            if hasattr(st, k):
                setattr(st, k, v)


async def apply_progress_payload(job_id: str, payload: dict[str, Any]) -> None:
    """Map pipeline progress dicts onto :class:`PipelineJobState` fields."""
    async with _jobs_lock:
        st = _jobs.get(job_id)
        if st is None:
            return
        phase = str(payload.get("phase") or "")
        st.phase = phase
        st.detail = str(payload.get("detail") or "")
        if payload.get("status") in ("section_complete", "question_complete"):
            if phase == "answer" and payload.get("status") == "section_complete":
                done = int(payload.get("completedSections") or 0)
                total = int(payload.get("totalSections") or 8)
                st.answer_completed = done
                st.answer_total = total
            elif phase == "validate":
                if payload.get("status") == "question_complete":
                    done = int(payload.get("completedQuestions") or 0)
                    total = int(payload.get("totalQuestions") or 64)
                else:
                    done = int(payload.get("completedSections") or 0)
                    total = int(payload.get("totalSections") or 8)
                st.validate_completed = done
                st.validate_total = total
