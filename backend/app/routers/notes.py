"""Visit notes.  (US-15, US-16)"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.auth import COORDINATOR, current_staff, require_role
from app.core.errors import not_found
from app.db.models import StaffMember
from app.db.session import get_db
from app.repositories import note_repo, visit_repo
from app.schemas.note import NoteCreate, NoteOut
from app.services import visit_service

router = APIRouter(prefix="/api/visits/{visit_id}/notes", tags=["Visit notes"], dependencies=[Depends(current_staff)])


@router.post("", response_model=NoteOut, status_code=status.HTTP_201_CREATED,
             responses={401: {}, 403: {}, 404: {}, 409: {"description": "Visit not COMPLETED"}, 422: {}},
             summary="Add a structured note to a COMPLETED visit (append-only)")
def add_note(visit_id: int, data: NoteCreate, db: Session = Depends(get_db),
             staff: StaffMember = Depends(require_role(COORDINATOR))):
    return visit_service.add_note(db, visit_id, data.observation_text, data.follow_up_actions, staff)


@router.get("", response_model=list[NoteOut], responses={404: {}}, summary="Source notes, oldest first")
def list_notes(visit_id: int, db: Session = Depends(get_db)):
    if visit_repo.get(db, visit_id) is None:
        raise not_found(f"Visit {visit_id}")
    return note_repo.list_for_visit(db, visit_id)