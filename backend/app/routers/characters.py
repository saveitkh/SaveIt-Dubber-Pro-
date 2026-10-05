from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Character, Project, User

router = APIRouter(prefix="/api/characters", tags=["characters"])


class CharacterPatch(BaseModel):
    name: str | None = None
    gender: str | None = None
    voiceId: str | None = None
    color: str | None = None
    emotionDefault: str | None = None
    speed: float | None = None
    mergeIntoId: str | None = None


def _owned_character(character_id: str, user: User, db: Session) -> Character:
    character = db.get(Character, character_id)
    if not character:
        raise HTTPException(status_code=404, detail="រកមិនឃើញតួអង្គ")
    project = db.get(Project, character.project_id)
    if not project or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="រកមិនឃើញតួអង្គ")
    return character


@router.patch("/{character_id}")
def patch_character(
    character_id: str,
    body: CharacterPatch,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    character = _owned_character(character_id, user, db)

    if body.mergeIntoId:
        target = _owned_character(body.mergeIntoId, user, db)
        for line in character.lines:
            line.character_id = target.id
            line.dirty = True
        db.delete(character)
        db.commit()
        return {"mergedInto": target.id}

    field_map = {"voiceId": "voice_id", "emotionDefault": "emotion_default"}
    for field, value in body.model_dump(exclude_unset=True, exclude={"mergeIntoId"}).items():
        setattr(character, field_map.get(field, field), value)
    db.commit()
    return {"id": character.id}
