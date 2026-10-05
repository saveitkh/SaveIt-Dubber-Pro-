import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.db import get_db
from app.deps import get_current_user
from app.jobs.runner import subscribe
from app.models import Job, Project, User

router = APIRouter(prefix="/api/jobs", tags=["jobs"])


@router.get("/{job_id}/events")
async def job_events(
    job_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> EventSourceResponse:
    job = db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="រកមិនឃើញការងារ")
    project = db.get(Project, job.project_id)
    if not project or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="រកមិនឃើញការងារ")

    async def event_generator():
        async for event in subscribe(job_id):
            yield {"event": "progress", "data": json.dumps(event)}

    return EventSourceResponse(event_generator())
