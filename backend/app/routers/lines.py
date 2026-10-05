from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.jobs.pipeline import regenerate_line as _regenerate_line
from app.models import Line, Project, ReviewItem, User

router = APIRouter(prefix="/api/lines", tags=["lines"])


class LinePatch(BaseModel):
    sourceText: str | None = None
    khmerText: str | None = None
    characterId: str | None = None
    startSec: float | None = None
    endSec: float | None = None
    emotion: str | None = None
    speed: float | None = None


def _owned_line(line_id: str, user: User, db: Session) -> Line:
    line = db.get(Line, line_id)
    if not line:
        raise HTTPException(status_code=404, detail="រកមិនឃើញបន្ទាត់")
    project = db.get(Project, line.project_id)
    if not project or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="រកមិនឃើញបន្ទាត់")
    return line


@router.patch("/{line_id}")
def patch_line(
    line_id: str, body: LinePatch, user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    line = _owned_line(line_id, user, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(line, {"sourceText": "source_text", "khmerText": "khmer_text", "characterId": "character_id",
                        "startSec": "start_sec", "endSec": "end_sec"}.get(field, field), value)
    line.dirty = True
    db.commit()
    return {"id": line.id, "dirty": line.dirty}


@router.post("/{line_id}/regenerate")
async def regenerate_line(line_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """Partial re-run (spec §6): re-synthesizes just this line, then rebuilds the
    mix and final export — fast, since no other line's audio is touched."""
    line = _owned_line(line_id, user, db)
    await _regenerate_line(line, db)
    db.refresh(line)
    return {
        "id": line.id,
        "dirty": line.dirty,
        "flags": line.flags,
        "audioPath": line.audio_path,
    }


@router.delete("/{line_id}")
def delete_line(line_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    line = _owned_line(line_id, user, db)
    db.query(ReviewItem).filter(ReviewItem.line_id == line.id).update({"resolved": True})
    db.delete(line)
    db.commit()
    return {"deleted": True}
