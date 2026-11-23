"""Visit scheduling and note rules.  (US-10 to US-15)

Allowed status changes (anything else -> 409):
    SCHEDULED -> SCHEDULED (new date)   reschedule; clash check runs again
    SCHEDULED -> COMPLETED              only if the visit date is today or earlier
    SCHEDULED -> MISSED                 only if the visit time has passed
    SCHEDULED -> CANCELLED              any time
    COMPLETED / MISSED / CANCELLED      final: a missed visit is rebooked as a new visit

Ownership: every visit is reached through participant_repo.get_scoped / visit_repo.get_scoped,
so a coordinator can only work on their own participants (others return 404).
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.auth import COORDINATOR, CurrentUser
from app.core.config import get_settings
from app.core.errors import ConflictError, FieldValidationError, NotFoundError
from app.core.logging_config import log_event
from app.db.models import Visit, VisitNote
from app.repositories import note_repo, participant_repo, staff_repo, visit_repo
from app.schemas.visit import VisitCreate, VisitUpdate
from app.services import audit_service

logger = logging.getLogger("app.visits")

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "SCHEDULED": {"COMPLETED", "MISSED", "CANCELLED"},
    "COMPLETED": set(),
    "MISSED": set(),
    "CANCELLED": set(),
}


def _check_coordinator(db: Session, code: str) -> None:
    staff = staff_repo.get_by_code(db, code)
    if staff is None or not staff.active or staff.role != COORDINATOR:
        raise FieldValidationError("coordinator_code", f"{code} is not an active coordinator")


def _check_clashes(db: Session, when: datetime, participant_id: int, coordinator_code: str,
                   exclude_visit_id: int | None = None) -> None:
    clash = visit_repo.find_clash(db, when, participant_id=participant_id, exclude_visit_id=exclude_visit_id)
    if clash:
        raise ConflictError(f"The participant already has visit {clash.visit_id} at this time",
                            code="DUPLICATE_TIME")
    clash = visit_repo.find_clash(db, when, coordinator_code=coordinator_code, exclude_visit_id=exclude_visit_id)
    if clash:
        raise ConflictError(f"{coordinator_code} already has visit {clash.visit_id} at this time",
                            code="DUPLICATE_TIME")


def visit_row(db: Session, user: CurrentUser, visit_id: int) -> dict:
    row = visit_repo.get_row(db, user, visit_id, get_settings().due_window_days)
    if row is None:
        raise NotFoundError(f"No visit {visit_id} found")
    return row


def schedule(db: Session, user: CurrentUser, data: VisitCreate) -> dict:
    participant = participant_repo.get_scoped(db, user, data.participant_id)
    if participant is None:
        raise NotFoundError(f"No participant {data.participant_id} found")
    if participant.consent_status != "ACTIVE":
        raise ConflictError("Consent is withdrawn for this participant. New visits cannot be scheduled.",
                            code="CONSENT_WITHDRAWN")
    coordinator = data.coordinator_code or participant.coordinator_code
    _check_coordinator(db, coordinator)
    _check_clashes(db, data.scheduled_for, participant.participant_id, coordinator)

    visit = visit_repo.add(db, Visit(participant_id=participant.participant_id, scheduled_for=data.scheduled_for,
                                     visit_type=data.visit_type, status="SCHEDULED", coordinator_code=coordinator))
    audit_service.record(db, entity_type="visit", entity_id=visit.visit_id, action="VISIT_SCHEDULED",
                         actor_code=user.staff_code, new_value="SCHEDULED")
    db.commit()
    log_event(logger, "visit_scheduled", visit_id=visit.visit_id, participant_id=participant.participant_id)
    return visit_row(db, user, visit.visit_id)


def update(db: Session, user: CurrentUser, visit_id: int, data: VisitUpdate) -> dict:
    visit = visit_repo.get_scoped(db, user, visit_id)
    if visit is None:
        raise NotFoundError(f"No visit {visit_id} found")
    if visit.status != "SCHEDULED":
        raise ConflictError(f"Visit {visit_id} is {visit.status}. Closed visits are final; book a new visit instead.",
                            code="VISIT_CLOSED")
    now = datetime.now(timezone.utc)
    changed = False

    if data.scheduled_for is not None and data.scheduled_for != visit.scheduled_for:
        if visit.participant.consent_status != "ACTIVE":
            raise ConflictError("Consent is withdrawn for this participant. The visit cannot be rescheduled.",
                                code="CONSENT_WITHDRAWN")
        _check_clashes(db, data.scheduled_for, visit.participant_id, visit.coordinator_code,
                       exclude_visit_id=visit.visit_id)
        audit_service.record(db, entity_type="visit", entity_id=visit.visit_id, action="VISIT_RESCHEDULED",
                             actor_code=user.staff_code,
                             old_value=visit.scheduled_for.isoformat(timespec="minutes"),
                             new_value=data.scheduled_for.isoformat(timespec="minutes"))
        visit.scheduled_for = data.scheduled_for
        changed = True

    if data.status is not None and data.status != visit.status:
        if data.status not in ALLOWED_TRANSITIONS[visit.status]:
            raise ConflictError(f"Cannot change status from {visit.status} to {data.status}",
                                code="INVALID_TRANSITION")
        if data.status == "COMPLETED" and visit.scheduled_for.astimezone(timezone.utc).date() > now.date():
            raise ConflictError("A future visit cannot be marked COMPLETED", code="INVALID_TRANSITION")
        if data.status == "MISSED" and visit.scheduled_for >= now:
            raise ConflictError("Only a visit whose time has passed can be marked MISSED", code="INVALID_TRANSITION")
        audit_service.record(db, entity_type="visit", entity_id=visit.visit_id, action="VISIT_STATUS_CHANGED",
                             actor_code=user.staff_code, old_value=visit.status, new_value=data.status)
        visit.status = data.status
        changed = True

    if not changed:
        raise ConflictError("No changes: the values match the current visit", code="NO_CHANGES")
    visit.updated_at = now
    db.commit()
    log_event(logger, "visit_updated", visit_id=visit.visit_id, status=visit.status)
    return visit_row(db, user, visit.visit_id)


def add_note(db: Session, user: CurrentUser, visit_id: int, observation_text: str,
             follow_up_actions: list[str]) -> VisitNote:
    """Notes only on COMPLETED visits; append-only (never edited or deleted).  (US-15)"""
    visit = visit_repo.get_scoped(db, user, visit_id)
    if visit is None:
        raise NotFoundError(f"No visit {visit_id} found")
    if visit.status != "COMPLETED":
        raise ConflictError(f"Notes can only be added to COMPLETED visits (visit {visit_id} is {visit.status})",
                            code="VISIT_NOT_COMPLETED")
    note = note_repo.add(db, VisitNote(visit_id=visit_id, observation_text=observation_text,
                                       follow_up_actions=follow_up_actions, author_code=user.staff_code))
    audit_service.record(db, entity_type="note", entity_id=note.note_id, action="NOTE_ADDED",
                         actor_code=user.staff_code, new_value=f"visit {visit_id}")
    db.commit()
    log_event(logger, "note_added", note_id=note.note_id, visit_id=visit_id)
    return note


def list_notes(db: Session, user: CurrentUser, visit_id: int) -> list[VisitNote]:
    if visit_repo.get_scoped(db, user, visit_id) is None:
        raise NotFoundError(f"No visit {visit_id} found")
    return note_repo.list_for_visit(db, visit_id)


def visit_detail(db: Session, user: CurrentUser, visit_id: int) -> dict:
    row = visit_row(db, user, visit_id)
    notes = note_repo.list_for_visit(db, visit_id)
    latest = visit_repo.latest_summary(db, visit_id)
    if not notes:
        state = "NO_NOTES"
    elif latest is None:
        state = "NOT_REQUESTED"
    elif latest.generation_status == "FAILED":
        state = "DRAFT_UNAVAILABLE"
    elif latest.review is None:
        state = "AWAITING_REVIEW"
    else:
        state = latest.review.decision
    summary = None if latest is None else {
        "summary_id": latest.summary_id, "generation_status": latest.generation_status,
        "error_code": latest.error_code, "created_at": latest.created_at,
        "review_decision": latest.review.decision if latest.review else None}
    return {**row, "notes": notes, "draft_state": state, "latest_summary": summary}