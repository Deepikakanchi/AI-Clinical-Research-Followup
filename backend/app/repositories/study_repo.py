"""
repositories/study_repo.py - SQL access for studies, owned by Rajnish Maurya.
Studies are shared reference data (not owned by any one staff member).

Used by routers/studies.py and services/participant_service.py.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Study


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