"""
routers/staff.py - Staff endpoint owned by Rajnish Maurya.
GET /api/staff: active reviewers for the "Assigned reviewer" dropdown (coordinators only).

Registered in main.py with: app.include_router(staff.router)
"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import COORDINATOR, REVIEWER, CurrentUser, require_role
from app.db.session import get_db
from app.repositories import staff_repo
from app.schemas.staff import StaffOut

router = APIRouter(prefix="/api/staff", tags=["Staff"])


@router.get("", response_model=list[StaffOut])
def list_reviewers(db: Session = Depends(get_db),
                   user: CurrentUser = Depends(require_role(COORDINATOR))) -> list[StaffOut]:
    # Coordinators never receive other coordinators' details.
    return [StaffOut.model_validate(s) for s in staff_repo.list_active_by_role(db, REVIEWER)]