"""Visit scheduling rules.  (US-10 to US-14)

Allowed status transitions (anything else -> 409):
    SCHEDULED -> SCHEDULED (new date)   reschedule, clash check runs again
    SCHEDULED -> COMPLETED              only if the visit date is today or earlier
    SCHEDULED -> MISSED                 only if the visit date is in the past
    SCHEDULED -> CANCELLED              any time
    COMPLETED / MISSED / CANCELLED      final: a missed visit is rebooked as a new visit
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import conflict, field_error, not_found
from app.core.logging_config import get_logger
from app.db.models import StaffMember, Visit
from app.repositories import participant_repo, staff_repo, visit_repo
from app.schemas.visit import VisitCreate, VisitUpdate
from app.services import audit_service

logger = get_logger("visits")

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "SCHEDULED": {"COMPLETED", "MISSED", "CANCELLED"},
    "COMPLETED": set(),
    "MISSED": set(),
    "CANCELLED": set(),
}


def _check_coordinator(db: Session, code: str) -> None:
    staff = staff_repo.get_by_code(db, code)
    if staff is None or not staff.active or staff.role != "COORDINATOR":
        raise field_error("coordinator_code", f"{code} is not an active coordinator")


def _check_clashes(db: Session, scheduled_for: datetime, participant_id: int, coordinator_code: str,
                   exclude_visit_id: int | None = None) -> None:
    clash = visit_repo.find_clash(db, scheduled_for, participant_id=participant_id, exclude_visit_id=exclude_visit_id)
    if clash:
        raise conflict(f"The participant already has visit {clash.visit_id} at this time", "DUPLICATE_TIME")
    clash = visit_repo.find_clash(db, scheduled_for, coordinator_code=coordinator_code, exclude_visit_id=exclude_visit_id)
    if clash:
        raise conflict(f"{coordinator_code} already has visit {clash.visit_id} at this time", "DUPLICATE_TIME")


def visit_row(db: Session, visit_id: int) -> dict:
    row = visit_repo.get_row(db, visit_id, settings.due_window_days)
    if row is None:
        raise not_found(f"Visit {visit_id}")
    return row


def schedule(db: Session, data: VisitCreate, staff: StaffMember) -> dict:
    participant = participant_repo.get(db, data.participant_id)
    if participant is None:
        raise not_found(f"Participant {data.participant_id}")
    if participant.consent_status != "ACTIVE":
        raise conflict("Consent is withdrawn for this participant. New visits cannot be scheduled.",
                       "CONSENT_WITHDRAWN")
    _check_coordinator(db, data.coordinator_code)
    _check_clashes(db, data.scheduled_for, data.participant_id, data.coordinator_code)
    visit = visit_repo.add(db, Visit(participant_id=data.participant_id, scheduled_for=data.scheduled_for,
                                     visit_type=data.visit_type, status="SCHEDULED",
                                     coordinator_code=data.coordinator_code))
    audit_service.record(db, "visit", visit.visit_id, "VISIT_SCHEDULED", staff.staff_code, None, "SCHEDULED")
    db.commit()
    logger.info("visit_scheduled id=%s participant_id=%s", visit.visit_id, data.participant_id)
    return visit_row(db, visit.visit_id)


def update(db: Session, visit_id: int, data: VisitUpdate, staff: StaffMember) -> dict:
    visit = visit_repo.get(db, visit_id)
    if visit is None:
        raise not_found(f"Visit {visit_id}")
    if visit.status != "SCHEDULED":
        raise conflict(f"Visit {visit_id} is {visit.status}. Closed visits are final; book a new visit instead.",
                       "VISIT_CLOSED")
    now = datetime.now(timezone.utc)
    changed = False

    new_coordinator = data.coordinator_code or visit.coordinator_code
    new_time = data.scheduled_for or visit.scheduled_for

    if data.scheduled_for is not None or data.coordinator_code is not None:
        if visit.participant.consent_status != "ACTIVE" and data.scheduled_for is not None:
            raise conflict("Consent is withdrawn for this participant. The visit cannot be rescheduled.",
                           "CONSENT_WITHDRAWN")
        if data.coordinator_code is not None:
            _check_coordinator(db, data.coordinator_code)
        _check_clashes(db, new_time, visit.participant_id, new_coordinator, exclude_visit_id=visit.visit_id)
        if data.scheduled_for is not None and data.scheduled_for != visit.scheduled_for:
            audit_service.record(db, "visit", visit.visit_id, "VISIT_RESCHEDULED", staff.staff_code,
                                 visit.scheduled_for.isoformat(timespec="minutes"),
                                 data.scheduled_for.isoformat(timespec="minutes"))
            visit.scheduled_for = data.scheduled_for
            changed = True
        if data.coordinator_code is not None and data.coordinator_code != visit.coordinator_code:
            audit_service.record(db, "visit", visit.visit_id, "COORDINATOR_CHANGED", staff.staff_code,
                                 visit.coordinator_code, data.coordinator_code)
            visit.coordinator_code = data.coordinator_code
            changed = True

    if data.status is not None and data.status != visit.status:
        if data.status not in ALLOWED_TRANSITIONS[visit.status]:
            raise conflict(f"Cannot change status from {visit.status} to {data.status}", "INVALID_TRANSITION")
        when = visit.scheduled_for
        if data.status == "COMPLETED" and when.astimezone(timezone.utc).date() > now.date():
            raise conflict("A future visit cannot be marked COMPLETED", "INVALID_TRANSITION")
        if data.status == "MISSED" and when >= now:
            raise conflict("Only a visit whose time has passed can be marked MISSED", "INVALID_TRANSITION")
        audit_service.record(db, "visit", visit.visit_id, "VISIT_STATUS_CHANGED", staff.staff_code,
                             visit.status, data.status)
        visit.status = data.status
        changed = True

    if not changed:
        raise conflict("No changes: the values match the current visit", "NO_CHANGES")
    visit.updated_at = now
    db.commit()
    logger.info("visit_updated id=%s status=%s", visit.visit_id, visit.status)
    return visit_row(db, visit.visit_id)


def add_note(db: Session, visit_id: int, observation_text: str, follow_up_actions: list[str],
             staff: StaffMember):
    """Notes are allowed only on COMPLETED visits and are append-only.  (US-15)"""
    from app.db.models import VisitNote
    from app.repositories import note_repo

    visit = visit_repo.get(db, visit_id)
    if visit is None:
        raise not_found(f"Visit {visit_id}")
    if visit.status != "COMPLETED":
        raise conflict(f"Notes can only be added to COMPLETED visits (visit {visit_id} is {visit.status})",
                       "VISIT_NOT_COMPLETED")
    note = note_repo.add(db, VisitNote(visit_id=visit_id, observation_text=observation_text,
                                       follow_up_actions=follow_up_actions, author_code=staff.staff_code))
    audit_service.record(db, "note", note.note_id, "NOTE_ADDED", staff.staff_code, None, f"visit {visit_id}")
    db.commit()
    logger.info("note_added id=%s visit_id=%s", note.note_id, visit_id)
    return note