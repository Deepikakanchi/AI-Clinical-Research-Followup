"""Audit trail (US-30). Everyone records events through record().

Call it inside the same transaction as the change; the caller commits.
Values must be short codes or statuses: anything longer than 60 characters
is refused, so note or draft text can never end up in the audit table.

Action names in use (keep to these):
  STUDY_CREATED, PARTICIPANT_ENROLLED, CONSENT_CHANGED,
  VISIT_SCHEDULED, VISIT_RESCHEDULED, VISIT_STATUS_CHANGED, NOTE_ADDED,
  AI_DRAFT_REQUESTED, REVIEW_APPROVED, REVIEW_REJECTED
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, owner_condition
from app.core.errors import NotFoundError
from app.db.models import AiSummary, AuditEvent, Participant, Study, SummaryReview, Visit, VisitNote
from app.repositories import audit_repo

ENTITY_TYPES = {"study", "participant", "visit", "note", "summary", "review"}
MAX_VALUE_LENGTH = 60


def record(db: Session, *, entity_type: str, entity_id: int, action: str, actor_code: str,
           old_value: str | None = None, new_value: str | None = None) -> AuditEvent:
    if entity_type not in ENTITY_TYPES:
        raise ValueError(f"Unknown audit entity_type: {entity_type}")
    for value in (old_value, new_value):
        if value is not None and len(value) > MAX_VALUE_LENGTH:
            raise ValueError("Audit values must be short codes or statuses, never free text")
    return audit_repo.add(db, AuditEvent(
        entity_type=entity_type, entity_id=entity_id, action=action,
        actor_code=actor_code, old_value=old_value, new_value=new_value,
    ))


def _entity_in_scope(db: Session, user: CurrentUser, entity_type: str, entity_id: int) -> bool:
    if entity_type == "study":
        return db.get(Study, entity_id) is not None      # studies are shared reference data

    if entity_type == "participant":
        query = select(Participant.participant_id).where(Participant.participant_id == entity_id)
    elif entity_type == "visit":
        query = (select(Visit.visit_id).join(Participant)
                 .where(Visit.visit_id == entity_id))
    elif entity_type == "note":
        query = (select(VisitNote.note_id).join(Visit).join(Participant)
                 .where(VisitNote.note_id == entity_id))
    elif entity_type == "summary":
        query = (select(AiSummary.summary_id).join(Visit).join(Participant)
                 .where(AiSummary.summary_id == entity_id))
    elif entity_type == "review":
        query = (select(SummaryReview.review_id)
                 .join(AiSummary, AiSummary.summary_id == SummaryReview.summary_id)
                 .join(Visit).join(Participant)
                 .where(SummaryReview.review_id == entity_id))
    else:
        return False
    return db.scalar(query.where(owner_condition(user))) is not None


def list_events(db: Session, user: CurrentUser, entity_type: str, entity_id: int) -> list[AuditEvent]:
    if not _entity_in_scope(db, user, entity_type, entity_id):
        raise NotFoundError(f"No {entity_type} {entity_id} found")
    return audit_repo.list_for_entity(db, entity_type, entity_id)