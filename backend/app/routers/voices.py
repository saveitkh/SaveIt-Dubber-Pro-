from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.config import VOICES_DIR
from app.db import get_db
from app.deps import get_current_user
from app.models import User, Voice

router = APIRouter(tags=["voices"])


def _voice_dict(voice: Voice) -> dict:
    return {
        "id": voice.id,
        "seriesId": voice.series_id,
        "name": voice.name,
        "referencePath": voice.reference_path,
        "fingerprint": voice.fingerprint,
        "providerIds": voice.provider_ids,
    }


@router.post("/api/voices/clip")
async def voice_clip_upload(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> dict:
    """Voice Clip intake (spec §4.1): background removal + speaker split + clip
    cutting run as a job in M3. M1 accepts the upload and stores it so the UI flow
    (drop file -> see groups -> name -> save) can be wired end to end."""
    dest = VOICES_DIR / f"clip_{user.id}_{file.filename}"
    with dest.open("wb") as out:
        out.write(await file.read())
    return {"stored": str(dest), "groups": []}


@router.post("/api/voices")
def save_voice(
    name: str = Form(...),
    series_id: str | None = Form(None),
    reference_path: str | None = Form(None),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    voice = Voice(name=name, series_id=series_id, reference_path=reference_path)
    db.add(voice)
    db.commit()
    return _voice_dict(voice)


@router.get("/api/series/{series_id}/voices")
def list_series_voices(
    series_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    voices = db.query(Voice).filter(Voice.series_id == series_id).all()
    return {"voices": [_voice_dict(v) for v in voices]}
