"""SQL access for audit_events (append-only: insert and read only)."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AuditEvent


def add(db: Session, event: AuditEvent) -> AuditEvent:
    db.add(event)
    db.flush()
    return event


def list_for_entity(db: Session, entity_type: str, entity_id: int) -> list[AuditEvent]:
    return list(db.scalars(
        select(AuditEvent)
        .where(AuditEvent.entity_type == entity_type, AuditEvent.entity_id == entity_id)
        .order_by(AuditEvent.created_at, AuditEvent.event_id)
    ))