import shutil

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.config import UPLOADS_DIR
from app.db import get_db
from app.deps import get_current_user
from app.jobs.pipeline import STAGES
from app.jobs.runner import run_job
from app.models import Character, Job, Line, Project, ReviewItem, User
from app.services import waveform as waveform_service

router = APIRouter(prefix="/api/projects", tags=["projects"])

ALLOWED_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".mp3", ".wav", ".m4a"}


def _project_dict(project: Project) -> dict:
    return {
        "id": project.id,
        "name": project.name,
        "seriesId": project.series_id,
        "status": project.status,
        "automationLevel": project.automation_level,
        "durationSec": project.duration_sec,
        "outputVideoPath": project.output_video_path,
        "outputAudioPath": project.output_audio_path,
        "outputSrtPath": project.output_srt_path,
        "createdAt": project.created_at.isoformat(),
    }


@router.post("")
async def create_project(
    background_tasks: BackgroundTasks,
    file: UploadFile | None = File(None),
    url: str | None = Form(None),
    name: str | None = Form(None),
    series_id: str | None = Form(None),
    automation_level: str = Form("full_auto"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    if not file and not url:
        raise HTTPException(status_code=400, detail="សូមដាក់ឯកសារវីដេអូ ឬតំណ (link)")

    project = Project(
        owner_id=user.id,
        series_id=series_id,
        name=name or (file.filename if file else url) or "Untitled",
        source_url=url,
        automation_level=automation_level,
        status="processing",
    )
    db.add(project)
    db.commit()

    if file:
        ext = ("." + file.filename.rsplit(".", 1)[-1].lower()) if "." in (file.filename or "") else ""
        if ext not in ALLOWED_EXTENSIONS:
            raise HTTPException(status_code=400, detail=f"ប្រភេទឯកសារមិនត្រូវបានគាំទ្រ: {ext}")
        dest = UPLOADS_DIR / f"{project.id}{ext}"
        with dest.open("wb") as out:
            shutil.copyfileobj(file.file, out)
        project.source_path = str(dest)
        db.commit()

    job = Job(project_id=project.id, stage=STAGES[0], status="queued")
    db.add(job)
    db.commit()

    background_tasks.add_task(run_job, job.id)

    return {"project": _project_dict(project), "jobId": job.id}


@router.get("/{project_id}")
def get_project(project_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    project = db.get(Project, project_id)
    if not project or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="រកមិនឃើញគម្រោង")

    lines = db.query(Line).filter(Line.project_id == project_id).order_by(Line.start_sec).all()
    characters = db.query(Character).filter(Character.project_id == project_id).all()
    review_items = (
        db.query(ReviewItem).filter(ReviewItem.project_id == project_id, ReviewItem.resolved.is_(False)).all()
    )
    jobs = db.query(Job).filter(Job.project_id == project_id).order_by(Job.created_at.desc()).all()

    return {
        "project": _project_dict(project),
        "lines": [
            {
                "id": line.id,
                "characterId": line.character_id,
                "startSec": line.start_sec,
                "endSec": line.end_sec,
                "sourceText": line.source_text,
                "khmerText": line.khmer_text,
                "emotion": line.emotion,
                "speed": line.speed,
                "audioPath": line.audio_path,
                "flags": line.flags,
                "dirty": line.dirty,
            }
            for line in lines
        ],
        "characters": [
            {
                "id": c.id,
                "name": c.name,
                "gender": c.gender,
                "voiceId": c.voice_id,
                "color": c.color,
                "faceThumbPath": c.face_thumb_path,
                "emotionDefault": c.emotion_default,
                "speed": c.speed,
            }
            for c in characters
        ],
        "reviewItems": [
            {"id": r.id, "lineId": r.line_id, "kind": r.kind, "payload": r.payload} for r in review_items
        ],
        "jobs": [
            {
                "id": j.id,
                "stage": j.stage,
                "status": j.status,
                "progress": j.progress,
                "message": j.message,
                "error": j.error,
            }
            for j in jobs
        ],
    }


@router.get("/{project_id}/waveform")
def get_waveform(
    project_id: str, track: str = "original", user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    """Server-computed waveform peaks for the timeline (spec §5.1)."""
    project = db.get(Project, project_id)
    if not project or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="រកមិនឃើញគម្រោង")

    path = {"original": project.audio_path, "background": project.background_path}.get(track)
    if not path:
        raise HTTPException(status_code=400, detail=f"ត្រាក់មិនត្រឹមត្រូវ ឬមិនទាន់មាន: {track}")

    return waveform_service.compute_peaks(path)


@router.get("")
def list_projects(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    projects = (
        db.query(Project).filter(Project.owner_id == user.id).order_by(Project.created_at.desc()).all()
    )
    out = []
    for p in projects:
        latest_job = (
            db.query(Job).filter(Job.project_id == p.id).order_by(Job.created_at.desc()).first()
        )
        d = _project_dict(p)
        d["latestJob"] = (
            {"id": latest_job.id, "stage": latest_job.stage, "status": latest_job.status, "progress": latest_job.progress}
            if latest_job
            else None
        )
        out.append(d)
    return {"projects": out}


@router.post("/{project_id}/run")
def run_from_stage(
    project_id: str,
    background_tasks: BackgroundTasks,
    stage: str = Form(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    project = db.get(Project, project_id)
    if not project or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="រកមិនឃើញគម្រោង")
    if stage not in STAGES:
        raise HTTPException(status_code=400, detail=f"ដំណាក់កាលមិនត្រឹមត្រូវ: {stage}")

    job = Job(project_id=project.id, stage=stage, status="queued")
    db.add(job)
    db.commit()

    background_tasks.add_task(run_job, job.id, stage)
    return {"jobId": job.id}
