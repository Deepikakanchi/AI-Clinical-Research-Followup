"""SQL access for visits, the dashboard, follow-ups and the review queue.  (US-05, US-13, US-14, US-22, US-26, US-28)

Every read is limited to the caller (same rule as owner_condition in core/auth.py):
a coordinator sees only participants they own, a reviewer only participants assigned to them.
Due / Overdue are calculated here in SQL, never stored and never by the AI.
Open follow-up actions are the reviewer's final actions on APPROVED summaries.
"""
from datetime import datetime

from sqlalchemy import select, text
from sqlalchemy.orm import Session, joinedload

from app.core.auth import CurrentUser, owner_condition
from app.db.models import AiSummary, Participant, Visit

# Same rule as owner_condition(), written in SQL for the raw queries below
SCOPE = """(
    (CAST(:role AS TEXT) = 'COORDINATOR' AND p.coordinator_code = CAST(:staff_code AS TEXT))
 OR (CAST(:role AS TEXT) = 'REVIEWER'    AND p.reviewer_code    = CAST(:staff_code AS TEXT))
)"""

_VISIT_COLUMNS = """
    v.visit_id, v.participant_id, p.participant_code, s.study_id, s.study_code,
    v.scheduled_for, v.visit_type, v.status, v.coordinator_code, p.reviewer_code,
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

VIEWS = {
    "upcoming": "v.status = 'SCHEDULED' AND v.scheduled_for >= NOW()",
    "due": "v.status = 'SCHEDULED' AND v.scheduled_for >= NOW() AND v.scheduled_for < NOW() + make_interval(days => :window)",
    "overdue": "v.status = 'SCHEDULED' AND v.scheduled_for < NOW()",
    "follow_up": "(v.status = 'MISSED' OR (v.status = 'SCHEDULED' AND v.scheduled_for < NOW()))",
}


def _scope_params(user: CurrentUser) -> dict:
    return {"role": user.role, "staff_code": user.staff_code}


def get_scoped(db: Session, user: CurrentUser, visit_id: int) -> Visit | None:
    return db.scalar(
        select(Visit).join(Participant)
        .options(joinedload(Visit.participant).joinedload(Participant.study))
        .where(Visit.visit_id == visit_id, owner_condition(user))
    )


def add(db: Session, visit: Visit) -> Visit:
    db.add(visit)
    db.flush()
    return visit


def list_visits(db: Session, user: CurrentUser, window: int, *, study_id: int | None = None,
                participant_id: int | None = None, status: str | None = None,
                date_from: datetime | None = None, date_to: datetime | None = None,
                view: str | None = None, newest_first: bool = False) -> list[dict]:
    conditions = [SCOPE]
    params = {"window": window, **_scope_params(user)}
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
        conditions.append(VIEWS[view])
    order = "v.scheduled_for DESC" if newest_first else "v.scheduled_for"
    sql = f"SELECT {_VISIT_COLUMNS} {_FROM} WHERE {' AND '.join(conditions)} ORDER BY {order}, v.visit_id"
    return [dict(r._mapping) for r in db.execute(text(sql), params)]


def get_row(db: Session, user: CurrentUser, visit_id: int, window: int) -> dict | None:
    sql = f"SELECT {_VISIT_COLUMNS} {_FROM} WHERE v.visit_id = :visit_id AND {SCOPE}"
    row = db.execute(text(sql), {"visit_id": visit_id, "window": window, **_scope_params(user)}).first()
    return dict(row._mapping) if row else None


def find_clash(db: Session, scheduled_for: datetime, *, participant_id: int | None = None,
               coordinator_code: str | None = None, exclude_visit_id: int | None = None) -> Visit | None:
    """A SCHEDULED visit at the same time for the same participant or coordinator (all owners)."""
    stmt = select(Visit).where(Visit.status == "SCHEDULED", Visit.scheduled_for == scheduled_for)
    if participant_id is not None:
        stmt = stmt.where(Visit.participant_id == participant_id)
    if coordinator_code is not None:
        stmt = stmt.where(Visit.coordinator_code == coordinator_code)
    if exclude_visit_id is not None:
        stmt = stmt.where(Visit.visit_id != exclude_visit_id)
    return db.scalar(stmt.limit(1))


def latest_summary(db: Session, visit_id: int) -> AiSummary | None:
    return db.scalar(
        select(AiSummary).options(joinedload(AiSummary.review))
        .where(AiSummary.visit_id == visit_id)
        .order_by(AiSummary.created_at.desc(), AiSummary.summary_id.desc()).limit(1)
    )


def follow_up_report(db: Session, user: CurrentUser, window: int, study_id: int | None) -> dict:
    """Dashboard counts (same rules as Q4 in database/queries.sql), for the caller's participants."""
    sql = f"""
    WITH p AS (
        SELECT p.* FROM participants p
        WHERE {SCOPE} AND (CAST(:study_id AS INTEGER) IS NULL OR p.study_id = CAST(:study_id AS INTEGER))
    ),
    v AS (SELECT v.* FROM visits v JOIN p ON p.participant_id = v.participant_id)
    SELECT
        (SELECT COUNT(*) FROM p WHERE p.consent_status = 'ACTIVE')                                   AS active_participants,
        (SELECT COUNT(*) FROM v WHERE v.status = 'SCHEDULED')                                         AS scheduled,
        (SELECT COUNT(*) FROM v WHERE v.status = 'SCHEDULED' AND v.scheduled_for >= NOW()
                                  AND v.scheduled_for < NOW() + make_interval(days => :window))       AS due_7_days,
        (SELECT COUNT(*) FROM v WHERE v.status = 'SCHEDULED' AND v.scheduled_for < NOW())            AS overdue,
        (SELECT COUNT(*) FROM v WHERE v.status = 'COMPLETED')                                         AS completed,
        (SELECT COUNT(*) FROM v WHERE v.status = 'MISSED')                                            AS missed,
        (SELECT COUNT(*) FROM v WHERE v.status = 'CANCELLED')                                         AS cancelled,
        (SELECT COALESCE(SUM(jsonb_array_length(r.final_follow_up_actions)), 0)
           FROM summary_reviews r JOIN ai_summaries a ON a.summary_id = r.summary_id
           JOIN v ON v.visit_id = a.visit_id
          WHERE r.decision = 'APPROVED')                                                              AS open_follow_up_actions,
        (SELECT COUNT(*) FROM ai_summaries a JOIN v ON v.visit_id = a.visit_id
           LEFT JOIN summary_reviews r ON r.summary_id = a.summary_id
          WHERE a.generation_status = 'SUCCEEDED' AND r.review_id IS NULL)                           AS awaiting_review
    """
    row = db.execute(text(sql),
                     {"study_id": study_id, "window": window, **_scope_params(user)}).first()
    return {k: int(v or 0) for k, v in row._mapping.items()}


def approved_follow_up_actions(db: Session, user: CurrentUser, study_id: int | None) -> list[dict]:
    """Follow-up actions confirmed by reviewers on APPROVED summaries, oldest decision first."""
    sql = f"""
    SELECT r.review_id, a.summary_id, a.visit_id, p.participant_code, s.study_code,
           r.reviewer_code, r.reviewed_at, r.final_follow_up_actions AS follow_up_actions
    FROM summary_reviews r
    JOIN ai_summaries a ON a.summary_id     = r.summary_id
    JOIN visits v       ON v.visit_id       = a.visit_id
    JOIN participants p ON p.participant_id = v.participant_id
    JOIN studies s      ON s.study_id       = p.study_id
    WHERE r.decision = 'APPROVED' AND jsonb_array_length(r.final_follow_up_actions) > 0 AND {SCOPE}
      AND (CAST(:study_id AS INTEGER) IS NULL OR s.study_id = CAST(:study_id AS INTEGER))
    ORDER BY r.reviewed_at
    """
    return [dict(r._mapping) for r in db.execute(text(sql), {"study_id": study_id, **_scope_params(user)})]


def review_queue(db: Session, user: CurrentUser, study_id: int | None) -> list[dict]:
    """Successful drafts with no review yet (Q3 in database/queries.sql), for the caller's participants."""
    sql = f"""
    SELECT a.summary_id, a.visit_id, v.scheduled_for AS visit_date, p.participant_code,
           s.study_code, a.created_at, 'AWAITING_REVIEW' AS review_state
    FROM ai_summaries a
    JOIN visits v               ON v.visit_id       = a.visit_id
    JOIN participants p         ON p.participant_id = v.participant_id
    JOIN studies s              ON s.study_id       = p.study_id
    LEFT JOIN summary_reviews r ON r.summary_id     = a.summary_id
    WHERE a.generation_status = 'SUCCEEDED' AND r.review_id IS NULL AND {SCOPE}
      AND (CAST(:study_id AS INTEGER) IS NULL OR s.study_id = CAST(:study_id AS INTEGER))
    ORDER BY a.created_at
    """
    return [dict(r._mapping) for r in db.execute(text(sql), {"study_id": study_id, **_scope_params(user)})]


def flagged_summaries(db: Session, user: CurrentUser, study_id: int | None) -> list[dict]:
    sql = f"""
    SELECT a.summary_id, a.visit_id, p.participant_code, s.study_code, r.reviewer_code, r.reviewed_at
    FROM summary_reviews r
    JOIN ai_summaries a ON a.summary_id     = r.summary_id
    JOIN visits v       ON v.visit_id       = a.visit_id
    JOIN participants p ON p.participant_id = v.participant_id
    JOIN studies s      ON s.study_id       = p.study_id
    WHERE r.follow_up_flag AND {SCOPE}
      AND (CAST(:study_id AS INTEGER) IS NULL OR s.study_id = CAST(:study_id AS INTEGER))
    ORDER BY r.reviewed_at
    """
    return [dict(r._mapping) for r in db.execute(text(sql), {"study_id": study_id, **_scope_params(user)})]