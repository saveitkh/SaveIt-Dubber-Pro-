import shutil

from fastapi import APIRouter

from app.config import settings

router = APIRouter(tags=["health"])


@router.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "demucs": shutil.which("demucs") is not None,
        "gpu": False,  # populated by a real CUDA probe when the GPU compose profile runs
        "providers": {
            "gemini": bool(settings.gemini_api_key),
            "elevenlabs": bool(settings.elevenlabs_api_key),
            "voxcpm": bool(settings.voxcpm_url),
        },
        "telegram": bool(settings.studio_telegram_bot_token),
    }
