from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Project, ReviewItem, User

router = APIRouter(prefix="/api/review-items", tags=["review-items"])


@router.post("/{item_id}/resolve")
def resolve_review_item(item_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    """"Correct" action on a Review queue card (spec §6): accept the automatic
    result as-is without regenerating anything."""
    item = db.get(ReviewItem, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="រកមិនឃើញធាតុ")
    project = db.get(Project, item.project_id)
    if not project or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="រកមិនឃើញធាតុ")

    item.resolved = True
    db.commit()

    unresolved = db.query(ReviewItem).filter(
        ReviewItem.project_id == project.id, ReviewItem.resolved.is_(False)
    ).count()
    if unresolved == 0 and project.status == "needs_review":
        project.status = "done"
        db.commit()

    return {"id": item.id, "resolved": True, "projectStatus": project.status}
