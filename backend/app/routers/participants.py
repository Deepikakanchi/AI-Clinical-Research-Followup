"""
routers/participants.py - Participant and consent endpoints owned by Rajnish Maurya .
(US-07, US-08, US-09)

GET/POST /api/participants, GET /api/participants/{id},
PATCH /api/participants/{id}/consent.
There is deliberately NO delete route: participants are only ever set to WITHDRAWN.

Registered in main.py with: app.include_router(participants.router)
"""
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.auth import COORDINATOR, CurrentUser, get_current_user, require_role
from app.db.session import get_db
from app.schemas.participant import ConsentUpdate, ParticipantCreate, ParticipantDetail, ParticipantOut
from app.services import participant_service

router = APIRouter(prefix="/api/participants", tags=["Participants"])


@router.get("", response_model=list[ParticipantOut])
def list_participants(study_id: int | None = Query(default=None, gt=0),
                      db: Session = Depends(get_db),
                      user: CurrentUser = Depends(get_current_user)) -> list[ParticipantOut]:
    """Coordinators get their own participants; reviewers get their assigned ones."""
    return participant_service.list_participants(db, user, study_id)


@router.post("", response_model=ParticipantOut, status_code=status.HTTP_201_CREATED)
def register_participant(body: ParticipantCreate, db: Session = Depends(get_db),
                         user: CurrentUser = Depends(require_role(COORDINATOR))) -> ParticipantOut:
    return participant_service.register(db, user, body)


@router.get("/{participant_id}", response_model=ParticipantDetail)
def get_participant(participant_id: int, db: Session = Depends(get_db),
                    user: CurrentUser = Depends(get_current_user)) -> ParticipantDetail:
    return participant_service.get_detail(db, user, participant_id)


@router.patch("/{participant_id}/consent", response_model=ParticipantOut)
def change_consent(participant_id: int, body: ConsentUpdate, db: Session = Depends(get_db),
                   user: CurrentUser = Depends(require_role(COORDINATOR))) -> ParticipantOut:
    return participant_service.change_consent(db, user, participant_id, body)