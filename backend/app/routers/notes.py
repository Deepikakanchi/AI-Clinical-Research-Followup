"""Visit notes.  (US-15, US-16)"""
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.core.auth import COORDINATOR, CurrentUser, get_current_user, require_role
from app.db.session import get_db
from app.schemas.note import NoteCreate, NoteOut
from app.services import visit_service

router = APIRouter(prefix="/api/visits/{visit_id}/notes", tags=["Visit notes"])


@router.post("", response_model=NoteOut, status_code=status.HTTP_201_CREATED,
             responses={401: {}, 403: {}, 404: {}, 409: {"description": "Visit not COMPLETED"}, 422: {}},
             summary="Add a structured note to a COMPLETED visit (append-only)")
def add_note(visit_id: int, data: NoteCreate, db: Session = Depends(get_db),
             user: CurrentUser = Depends(require_role(COORDINATOR))):
    return visit_service.add_note(db, user, visit_id, data.observation_text, data.follow_up_actions)


@router.get("", response_model=list[NoteOut], responses={401: {}, 404: {}}, summary="Source notes, oldest first")
def list_notes(visit_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    return visit_service.list_notes(db, user, visit_id)