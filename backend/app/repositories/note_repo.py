"""Visit note SQL access. Append-only: insert and read, never update or delete."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import VisitNote


def add(db: Session, note: VisitNote) -> VisitNote:
    db.add(note)
    db.flush()
    return note


def list_for_visit(db: Session, visit_id: int) -> list[VisitNote]:
    return list(db.scalars(select(VisitNote).where(VisitNote.visit_id == visit_id)
                           .order_by(VisitNote.created_at, VisitNote.note_id)))


def count_for_visit(db: Session, visit_id: int) -> int:
    return db.scalar(select(func.count()).select_from(VisitNote).where(VisitNote.visit_id == visit_id)) or 0