"""
core/auth.py - Login tokens, current user, role checks and ownership rule,
owned by Rajnish Maurya.  (US-27)

How it works
------------
1. POST /api/auth/login checks email + password against the users table
   (bcrypt hash) and returns a signed token (JWT) holding only the staff_code.
2. Every other request sends "Authorization: Bearer <token>".
   get_current_user() verifies the token and RELOADS the staff member from
   the database, so the role always comes from the database, and a staff
   member set to inactive loses access immediately.
3. require_role("REVIEWER") etc. returns 403 for the wrong role.
4. owner_condition(user) is the ownership filter every query must apply:
   a coordinator sees only participants they own, a reviewer only the
   participants assigned to them. Records outside the scope return 404.

Persons 2 and 3: add Depends(get_current_user) or Depends(require_role(...))
to every route, and join every query to Participant with
    .where(owner_condition(user))
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import ColumnElement, false
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ForbiddenError, UnauthorizedError
from app.db.models import Participant, StaffMember
from app.db.session import get_db

COORDINATOR = "COORDINATOR"
REVIEWER = "REVIEWER"

HOME_PATHS = {
    COORDINATOR: "/coordinator/dashboard",
    REVIEWER: "/reviewer/queue",
}

_bearer = HTTPBearer(auto_error=False, description="Token from POST /api/auth/login")

# Used when the email is unknown, so a failed login takes as long as a wrong password
# and response times do not reveal which emails exist.
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt(rounds=12))


def hash_password(password: str) -> str:
    """bcrypt hash (same format as PostgreSQL pgcrypto crypt(..., gen_salt('bf')))."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str | None) -> bool:
    candidate = password.encode("utf-8")
    if len(candidate) > 72:                  # bcrypt's limit; longer input can never match
        return False
    try:
        if password_hash is None:
            bcrypt.checkpw(candidate, _DUMMY_HASH)
            return False
        return bcrypt.checkpw(candidate, password_hash.encode("utf-8"))
    except ValueError:                       # malformed hash in the database
        return False


@dataclass(frozen=True)
class CurrentUser:
    staff_code: str
    role: str
    display_label: str

    @property
    def home_path(self) -> str:
        return HOME_PATHS[self.role]


def create_access_token(staff: StaffMember) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    payload = {
        "sub": staff.staff_code,
        "iat": now,
        "exp": now + timedelta(minutes=settings.jwt_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise UnauthorizedError("Sign in to continue")

    settings = get_settings()
    try:
        payload = jwt.decode(credentials.credentials, settings.jwt_secret,
                             algorithms=[settings.jwt_algorithm],
                             options={"require": ["sub", "exp"]})
    except jwt.PyJWTError:
        raise UnauthorizedError("Your session has expired or is invalid. Please sign in again") from None

    staff = db.query(StaffMember).filter(StaffMember.staff_code == payload["sub"]).one_or_none()
    if staff is None or not staff.active:
        raise UnauthorizedError("Your session has expired or is invalid. Please sign in again")

    return CurrentUser(staff_code=staff.staff_code, role=staff.role, display_label=staff.display_label)


def require_role(*roles: str):
    """Dependency factory: Depends(require_role(COORDINATOR)) allows coordinators only."""
    allowed = set(roles)

    def checker(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if user.role not in allowed:
            names = " or ".join(sorted(r.lower() + "s" for r in allowed))
            raise ForbiddenError(f"Only {names} can do this")
        return user

    return checker


def owner_condition(user: CurrentUser) -> ColumnElement[bool]:
    """WHERE clause limiting Participant rows (and anything joined to them) to the caller."""
    if user.role == COORDINATOR:
        return Participant.coordinator_code == user.staff_code
    if user.role == REVIEWER:
        return Participant.reviewer_code == user.staff_code
    return false()