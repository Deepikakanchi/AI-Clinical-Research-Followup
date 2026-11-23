"""
routers/audit.py - Audit endpoint owned by Rajnish Maurya.  (US-30)
GET /api/audit-events: history of one record, only within the caller's scope.

Registered in main.py with: app.include_router(audit.router)
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user
from app.db.session import get_db
from app.schemas.audit import AuditEventOut, EntityType
from app.services import audit_service

router = APIRouter(prefix="/api/audit-events", tags=["Audit"])


@router.get("", response_model=list[AuditEventOut])
def list_audit_events(entity_type: EntityType = Query(...),
                      entity_id: int = Query(..., gt=0),
                      db: Session = Depends(get_db),
                      user: CurrentUser = Depends(get_current_user)) -> list[AuditEventOut]:
    events = audit_service.list_events(db, user, entity_type, entity_id)
    return [AuditEventOut.model_validate(e) for e in events]