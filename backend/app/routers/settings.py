import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings as app_settings
from app.db import get_db
from app.deps import require_admin
from app.models import SettingRow, User
from app.services import elevenlabs_service, gemini_client, voxcpm_client

router = APIRouter(prefix="/api/settings", tags=["settings"])


def _provider_status() -> dict:
    return {
        "gemini": {"configured": bool(app_settings.gemini_api_key)},
        "elevenlabs": {"configured": bool(app_settings.elevenlabs_api_key)},
        "voxcpm": {"configured": bool(app_settings.voxcpm_url), "url": app_settings.voxcpm_url},
    }


class ProvidersPayload(BaseModel):
    fallbackOrder: list[str] = ["gemini", "voxcpm", "elevenlabs"]


@router.get("/providers")
def get_providers(user: User = Depends(require_admin), db: Session = Depends(get_db)) -> dict:
    row = db.get(SettingRow, "providers")
    return {"status": _provider_status(), "config": row.value if row else {}}


@router.put("/providers")
def put_providers(
    body: ProvidersPayload, user: User = Depends(require_admin), db: Session = Depends(get_db)
) -> dict:
    row = db.get(SettingRow, "providers")
    if not row:
        row = SettingRow(key="providers", value={})
        db.add(row)
    row.value = body.model_dump()
    db.commit()
    return {"status": _provider_status(), "config": row.value}


@router.post("/providers/{name}/test")
async def test_provider(name: str, user: User = Depends(require_admin)) -> dict:
    status = _provider_status().get(name)
    if status is None:
        return {"ok": False, "reason": f"មិនស្គាល់អ្នកផ្តល់សេវា: {name}"}
    if not status.get("configured"):
        return {"ok": False, "reason": "មិនទាន់កំណត់គន្លឹះ (API key) ទេ"}

    if name == "elevenlabs":
        return await elevenlabs_service.check_status(app_settings.elevenlabs_api_key)
    if name == "voxcpm":
        return await voxcpm_client.check_status(app_settings.voxcpm_url)
    if name == "gemini":
        async with httpx.AsyncClient(timeout=15) as client:
            try:
                resp = await client.get(
                    f"{gemini_client.API_ROOT}/models",
                    headers={"x-goog-api-key": app_settings.gemini_api_key},
                )
            except httpx.HTTPError as exc:
                return {"ok": False, "reason": str(exc)}
        return {"ok": resp.status_code == 200, "reason": f"HTTP {resp.status_code}" if resp.status_code != 200 else "OK"}

    return {"ok": True, "reason": "បានកំណត់រចនាសម្ព័ន្ធ"}
