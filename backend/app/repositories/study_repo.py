"""
repositories/study_repo.py - SQL access for studies, owned by Rajnish Maurya.
Studies are shared reference data (not owned by any one staff member).

Used by routers/studies.py and services/participant_service.py.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, owner_condition
from app.db.models import Participant, Study

def list_all(db: Session) -> list[Study]:
    return list(db.scalars(select(Study).order_by(Study.study_code)))


def get(db: Session, study_id: int) -> Study | None:
    return db.get(Study, study_id)


def get_for_update(db: Session, study_id: int) -> Study | None:
    """Locks the study row so participant codes in one study are generated one at a time."""
    return db.scalar(select(Study).where(Study.study_id == study_id).with_for_update())


def get_by_code(db: Session, study_code: str) -> Study | None:
    return db.scalar(select(Study).where(Study.study_code == study_code))


def add(db: Session, study: Study) -> Study:
    db.add(study)
    db.flush()
    return study


def participant_counts(db: Session, user: CurrentUser) -> dict[int, tuple[int, int, int]]:
    """Per study: (all participants, active participants, the caller's own participants).

    The first two are aggregate numbers across every coordinator; no participant
    codes or details are returned, so other coordinators' records stay private.
    """
    rows = db.execute(
        select(
            Participant.study_id,
            func.count(),
            func.count().filter(Participant.consent_status == "ACTIVE"),
            func.count().filter(owner_condition(user)),
        ).group_by(Participant.study_id)
    )
    return {study_id: (total, active, mine) for study_id, total, active, mine in rows}