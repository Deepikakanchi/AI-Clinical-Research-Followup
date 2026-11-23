"""
services/participant_service.py - Participant registration and consent rules,
owned by Rajnish Maurya.  (US-07, US-08, US-09)

Ownership: the registering coordinator owns the participant; the chosen reviewer
is assigned to it. Other staff cannot see it (404).

Persons 2 and 3 load participants with get_in_scope(db, user, participant_id).
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.auth import REVIEWER, CurrentUser
from app.core.errors import ConflictError, FieldValidationError, NotFoundError
from app.core.logging_config import log_event
from app.db.models import Participant
from app.repositories import participant_repo, staff_repo, study_repo
from app.schemas.participant import (ConsentUpdate, ParticipantCreate, ParticipantDetail,
                                     ParticipantOut, ParticipantVisit)
from app.services import audit_service

logger = logging.getLogger("app.participants")
MAX_CODE_NUMBER = 9999


def to_out(p: Participant) -> ParticipantOut:
    return ParticipantOut(
        participant_id=p.participant_id, study_id=p.study_id, study_code=p.study.study_code,
        participant_code=p.participant_code, consent_status=p.consent_status,
        coordinator_code=p.coordinator_code, reviewer_code=p.reviewer_code,
        enrolled_at=p.enrolled_at, consent_updated_at=p.consent_updated_at,
    )


def get_in_scope(db: Session, user: CurrentUser, participant_id: int,
                 for_update: bool = False) -> Participant:
    """Persons 2 and 3: use this to load a participant; it raises 404 outside the scope."""
    participant = participant_repo.get_scoped(db, user, participant_id, for_update=for_update)
    if participant is None:
        raise NotFoundError(f"Participant {participant_id} not found")
    return participant


def list_participants(db: Session, user: CurrentUser, study_id: int | None) -> list[ParticipantOut]:
    return [to_out(p) for p in participant_repo.list_scoped(db, user, study_id)]


def get_detail(db: Session, user: CurrentUser, participant_id: int) -> ParticipantDetail:
    participant = get_in_scope(db, user, participant_id)
    visits = participant_repo.visits_newest_first(db, participant_id)
    return ParticipantDetail(
        **to_out(participant).model_dump(),
        visits=[ParticipantVisit.model_validate(v) for v in visits],
    )


def register(db: Session, user: CurrentUser, data: ParticipantCreate) -> ParticipantOut:
    study = study_repo.get_for_update(db, data.study_id)   # lock: one code at a time per study
    if study is None:
        raise NotFoundError(f"Study {data.study_id} not found")
    if not study.active:
        raise ConflictError(f"Study {study.study_code} is not active")

    reviewer = staff_repo.get_by_code(db, data.reviewer_code)
    if reviewer is None or reviewer.role != REVIEWER or not reviewer.active:
        raise FieldValidationError("reviewer_code", "Choose a valid reviewer")

    number = participant_repo.next_code_number(db, study.study_id)
    if number > MAX_CODE_NUMBER:
        raise ConflictError("Participant code limit reached for this study")

    participant = participant_repo.add(db, Participant(
        study_id=study.study_id,
        participant_code=f"P-{number:04d}",
        consent_status=data.consent_status,
        coordinator_code=user.staff_code,          # owner = the logged-in coordinator
        reviewer_code=reviewer.staff_code,
    ))
    audit_service.record(db, entity_type="participant", entity_id=participant.participant_id,
                         action="PARTICIPANT_ENROLLED", actor_code=user.staff_code,
                         new_value=data.consent_status)
    db.commit()
    db.refresh(participant)
    log_event(logger, "participant_registered", participant_id=participant.participant_id,
              study_id=study.study_id, actor=user.staff_code)
    return to_out(participant)


def change_consent(db: Session, user: CurrentUser, participant_id: int,
                   data: ConsentUpdate) -> ParticipantOut:
    participant = get_in_scope(db, user, participant_id, for_update=True)
    if participant.consent_status == data.consent_status:
        raise ConflictError(f"Consent is already {data.consent_status}")

    old_status = participant.consent_status
    participant.consent_status = data.consent_status
    participant.consent_updated_at = datetime.now(timezone.utc)
    audit_service.record(db, entity_type="participant", entity_id=participant.participant_id,
                         action="CONSENT_CHANGED", actor_code=user.staff_code,
                         old_value=old_status, new_value=data.consent_status)
    db.commit()
    db.refresh(participant)
    log_event(logger, "consent_changed", participant_id=participant.participant_id,
              old_value=old_status, new_value=data.consent_status, actor=user.staff_code)
    return to_out(participant)