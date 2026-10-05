"""Background job runner + SSE broadcaster.

M1: drives the 8-stage pipeline (spec §3) with stub stage functions so the whole
upload -> live-progress -> resumable-job loop works end to end over SSE. M2 replaces
each stage body in `pipeline.py` with the real ffmpeg/Demucs/Gemini/TTS calls; this
runner, the DB bookkeeping and the SSE wire format do not need to change.
"""

import asyncio
from collections.abc import AsyncIterator

from app.db import SessionLocal
from app.jobs.pipeline import STAGES, run_stage
from app.models import Job

_queues: dict[str, list[asyncio.Queue]] = {}


def _broadcast(job_id: str, event: dict) -> None:
    for q in _queues.get(job_id, []):
        q.put_nowait(event)


async def subscribe(job_id: str) -> AsyncIterator[dict]:
    queue: asyncio.Queue = asyncio.Queue()
    _queues.setdefault(job_id, []).append(queue)
    try:
        # Replay current state immediately so a late subscriber / page reload
        # catches up instead of waiting for the next stage transition.
        db = SessionLocal()
        try:
            job = db.get(Job, job_id)
            if job:
                yield {
                    "stage": job.stage,
                    "status": job.status,
                    "progress": job.progress,
                    "message": job.message,
                    "error": job.error,
                }
                if job.status in ("done", "error"):
                    return
        finally:
            db.close()

        while True:
            event = await queue.get()
            yield event
            if event.get("status") in ("done", "error"):
                return
    finally:
        _queues.get(job_id, []).remove(queue)


async def run_job(job_id: str, from_stage: str | None = None) -> None:
    db = SessionLocal()
    try:
        job = db.get(Job, job_id)
        if not job:
            return
        job.status = "running"
        db.commit()

        stages = STAGES
        if from_stage and from_stage in stages:
            stages = stages[stages.index(from_stage) :]

        for stage in stages:
            job.stage = stage
            job.message = None
            db.commit()

            def on_progress(progress: float, message: str | None = None, stage: str = stage) -> None:
                job.progress = progress
                job.message = message
                db.commit()
                _broadcast(
                    job_id,
                    {"stage": stage, "status": "running", "progress": progress, "message": message},
                )

            try:
                await run_stage(stage, job.project_id, db, on_progress)
            except Exception as exc:  # noqa: BLE001
                job.status = "error"
                job.error = str(exc)
                db.commit()
                _broadcast(job_id, {"stage": stage, "status": "error", "progress": job.progress, "error": str(exc)})
                return

        job.status = "done"
        job.progress = 100.0
        db.commit()
        _broadcast(job_id, {"stage": job.stage, "status": "done", "progress": 100.0, "message": None})
    finally:
        db.close()
