"""Visit SQL access, including the queries from database/queries.sql.  (US-05, US-13)

Due / Overdue labels are calculated here in SQL, never stored and never by the AI.
"""
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session, joinedload

from app.db.models import Participant, Visit

_VISIT_COLUMNS = """
    v.visit_id, v.participant_id, p.participant_code, s.study_id, s.study_code,
    v.scheduled_for, v.visit_type, v.status, v.coordinator_code,
    CASE
        WHEN v.status = 'SCHEDULED' AND v.scheduled_for < NOW() THEN 'OVERDUE'
        WHEN v.status = 'SCHEDULED' AND v.scheduled_for < NOW() + make_interval(days => :window) THEN 'DUE'
    END AS due_label
"""
_FROM = """
FROM visits v
JOIN participants p ON p.participant_id = v.participant_id
JOIN studies s      ON s.study_id       = p.study_id
"""

# view -> SQL condition
_VIEWS = {
    "upcoming": "v.status = 'SCHEDULED' AND v.scheduled_for >= NOW()",
    "due": "v.status = 'SCHEDULED' AND v.scheduled_for >= NOW() AND v.scheduled_for < NOW() + make_interval(days => :window)",
    "overdue": "v.status = 'SCHEDULED' AND v.scheduled_for < NOW()",
    "follow_up": "(v.status = 'MISSED' OR (v.status = 'SCHEDULED' AND v.scheduled_for < NOW()))",
}


def get(db: Session, visit_id: int) -> Visit | None:
    return db.scalar(select(Visit).options(joinedload(Visit.participant).joinedload(Participant.study))
                     .where(Visit.visit_id == visit_id))


def add(db: Session, visit: Visit) -> Visit:
    db.add(visit)
    db.flush()
    return visit


def list_visits(db: Session, window: int, *, study_id: int | None = None, participant_id: int | None = None,
                status: str | None = None, date_from: datetime | None = None, date_to: datetime | None = None,
                view: str | None = None, newest_first: bool = False) -> list[dict]:
    conditions, params = [], {"window": window}
    if study_id is not None:
        conditions.append("s.study_id = :study_id"); params["study_id"] = study_id
    if participant_id is not None:
        conditions.append("v.participant_id = :participant_id"); params["participant_id"] = participant_id
    if status:
        conditions.append("v.status = :status"); params["status"] = status
    if date_from:
        conditions.append("v.scheduled_for >= :date_from"); params["date_from"] = date_from
    if date_to:
        conditions.append("v.scheduled_for <= :date_to"); params["date_to"] = date_to
    if view and view != "all":
        conditions.append(_VIEWS[view])
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    order = "v.scheduled_for DESC" if newest_first else "v.scheduled_for"
    sql = f"SELECT {_VISIT_COLUMNS} {_FROM} {where} ORDER BY {order}, v.visit_id"
    return [dict(r._mapping) for r in db.execute(text(sql), params)]


def get_row(db: Session, visit_id: int, window: int) -> dict | None:
    sql = f"SELECT {_VISIT_COLUMNS} {_FROM} WHERE v.visit_id = :visit_id"
    row = db.execute(text(sql), {"visit_id": visit_id, "window": window}).first()
    return dict(row._mapping) if row else None


def find_clash(db: Session, scheduled_for: datetime, *, participant_id: int | None = None,
               coordinator_code: str | None = None, exclude_visit_id: int | None = None) -> Visit | None:
    """A SCHEDULED visit at the same time for the same participant or coordinator."""
    stmt = select(Visit).where(Visit.status == "SCHEDULED", Visit.scheduled_for == scheduled_for)
    if participant_id is not None:
        stmt = stmt.where(Visit.participant_id == participant_id)
    if coordinator_code is not None:
        stmt = stmt.where(Visit.coordinator_code == coordinator_code)
    if exclude_visit_id is not None:
        stmt = stmt.where(Visit.visit_id != exclude_visit_id)
    return db.scalar(stmt.limit(1))


def follow_up_report(db: Session, window: int, study_id: int | None) -> dict:
    """Same numbers as Q4 in database/queries.sql, optionally for one study."""
    sql = """
    WITH v AS (
        SELECT v.* FROM visits v JOIN participants p ON p.participant_id = v.participant_id
        WHERE CAST(:study_id AS INTEGER) IS NULL OR p.study_id = CAST(:study_id AS INTEGER)
    )
    SELECT
        (SELECT COUNT(*) FROM participants p WHERE p.consent_status = 'ACTIVE'
            AND (CAST(:study_id AS INTEGER) IS NULL OR p.study_id = CAST(:study_id AS INTEGER)))      AS active_participants,
        COUNT(*) FILTER (WHERE v.status = 'SCHEDULED')                                               AS scheduled,
        COUNT(*) FILTER (WHERE v.status = 'SCHEDULED' AND v.scheduled_for >= NOW()
                           AND v.scheduled_for < NOW() + make_interval(days => :window))             AS due_7_days,
        COUNT(*) FILTER (WHERE v.status = 'SCHEDULED' AND v.scheduled_for < NOW())                   AS overdue,
        COUNT(*) FILTER (WHERE v.status = 'COMPLETED')                                               AS completed,
        COUNT(*) FILTER (WHERE v.status = 'MISSED')                                                  AS missed,
        COUNT(*) FILTER (WHERE v.status = 'CANCELLED')                                               AS cancelled,
        (SELECT COALESCE(SUM(jsonb_array_length(n.follow_up_actions)), 0) FROM visit_notes n
            WHERE n.visit_id IN (SELECT visit_id FROM v))                                            AS open_follow_up_actions,
        (SELECT COUNT(*) FROM ai_summaries a LEFT JOIN summary_reviews r ON r.summary_id = a.summary_id
            WHERE a.generation_status = 'SUCCEEDED' AND r.review_id IS NULL
              AND a.visit_id IN (SELECT visit_id FROM v))                                            AS awaiting_review
    FROM v
    """
    row = db.execute(text(sql), {"study_id": study_id, "window": window}).first()
    return {k: int(v or 0) for k, v in row._mapping.items()}


def notes_with_actions(db: Session, study_id: int | None) -> list[dict]:
    sql = """
    SELECT n.note_id, n.visit_id, p.participant_code, s.study_code, n.created_at, n.follow_up_actions
    FROM visit_notes n
    JOIN visits v       ON v.visit_id       = n.visit_id
    JOIN participants p ON p.participant_id = v.participant_id
    JOIN studies s      ON s.study_id       = p.study_id
    WHERE jsonb_array_length(n.follow_up_actions) > 0
      AND (CAST(:study_id AS INTEGER) IS NULL OR s.study_id = CAST(:study_id AS INTEGER))
    ORDER BY n.created_at
    """
    return [dict(r._mapping) for r in db.execute(text(sql), {"study_id": study_id})]