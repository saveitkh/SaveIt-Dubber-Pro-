import asyncio
import uuid

import numpy as np
from fastapi import APIRouter, Depends, File, Form, UploadFile
from sqlalchemy.orm import Session

from app.config import VOICES_DIR
from app.db import get_db
from app.deps import get_current_user
from app.models import User, Voice
from app.services import vocal_separator, voice_cast_store, voice_engine

router = APIRouter(tags=["voices"])

# segment_fingerprint() layout: [13 MFCC means, 13 MFCC stds, pitch_hz, voiced_ratio]
_PITCH_INDEX = 26
_FEMALE_PITCH_THRESHOLD_HZ = 165.0


def _voice_dict(voice: Voice) -> dict:
    return {
        "id": voice.id,
        "seriesId": voice.series_id,
        "name": voice.name,
        "referencePath": voice.reference_path,
        "fingerprint": voice.fingerprint,
        "providerIds": voice.provider_ids,
    }


@router.get("/api/voices")
def list_voices(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    voices = db.query(Voice).all()
    return {"voices": [_voice_dict(v) for v in voices]}


@router.post("/api/voices/clip")
async def voice_clip_upload(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
) -> dict:
    """Voice Clip (spec §4.1): drop any audio/video with voices -> remove background
    -> split by speaker -> cut into clips -> auto-pick the best reference per voice.
    Runs inline (not as a tracked Job) since a voice sample is short; the heavier
    per-project pipeline stages are what get the SSE job treatment."""
    work_dir = VOICES_DIR / f"clip_{user.id}_{uuid.uuid4().hex[:12]}"
    work_dir.mkdir(parents=True, exist_ok=True)

    upload_path = work_dir / (file.filename or "upload")
    with upload_path.open("wb") as out:
        out.write(await file.read())

    separated = await vocal_separator.separate_vocals_and_bgm(str(upload_path), str(work_dir / "separated"))
    vocals_path = separated["vocalsPath"]

    audio, sr = await asyncio.to_thread(voice_engine.load_audio_16k_mono, vocals_path)
    segments = voice_engine.detect_speech_segments(audio, sr)
    if len(segments) < 1:
        return {"groups": [], "workDir": work_dir.name}

    feats = voice_engine.extract_features(audio, sr, segments)
    k_hi = min(6, len(segments))
    labels, k, _ = voice_engine.cluster_segments(feats, k=None, k_range=(1, max(1, k_hi)))

    groups = []
    for c in range(k):
        idxs = [i for i, label in enumerate(labels) if int(label) == c]
        if not idxs:
            continue
        spans = [segments[i] for i in idxs]
        avg_pitch = float(np.mean(feats[idxs, _PITCH_INDEX]))
        gender = "female" if avg_pitch >= _FEMALE_PITCH_THRESHOLD_HZ else "male"

        out_path = work_dir / f"group_{c}.wav"
        built_path, total_sec = await voice_cast_store.build_reference_clip(vocals_path, spans, str(out_path))
        quality = "too_short" if total_sec < 3 else ("best" if total_sec >= 10 else "ok")

        groups.append({
            "groupId": c,
            "gender": gender,
            "totalSeconds": round(total_sec, 1),
            "clipCount": len(spans),
            "quality": quality,
            "previewPath": f"/media/voices/{work_dir.name}/group_{c}.wav" if built_path else None,
        })

    groups.sort(key=lambda g: g["totalSeconds"], reverse=True)
    return {"groups": groups, "workDir": work_dir.name}


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
