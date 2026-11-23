"""
repositories/staff_repo.py - SQL access for staff_members, owned by Rajnish Maurya.
No business rules here.

Used by routers/staff.py (reviewer dropdown) and services/participant_service.py
(checking the assigned reviewer).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import StaffMember


def get_by_code(db: Session, staff_code: str) -> StaffMember | None:
    return db.scalar(select(StaffMember).where(StaffMember.staff_code == staff_code))


def list_active_by_role(db: Session, role: str) -> list[StaffMember]:
    return list(db.scalars(
        select(StaffMember)
        .where(StaffMember.role == role, StaffMember.active.is_(True))
        .order_by(StaffMember.staff_code)
    ))