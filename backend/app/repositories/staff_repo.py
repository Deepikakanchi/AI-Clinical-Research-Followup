"""SQL access for staff_members. No business rules here."""
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