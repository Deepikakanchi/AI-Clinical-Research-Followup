"""
repositories/user_repo.py - SQL access for login accounts (users table),
owned by Rajnish Maurya. No business rules here.

Used by routers/auth.py to find the account for an email at login.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.db.models import User


def get_by_email(db: Session, email: str) -> User | None:
    """Loads the login account together with its staff member (role, active flag)."""
    return db.scalar(
        select(User)
        .options(joinedload(User.staff))
        .where(User.email == email.strip().lower())
    )