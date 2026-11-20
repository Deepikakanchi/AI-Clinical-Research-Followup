"""POST /api/auth/login (email + password) and GET /api/auth/me.

Flow:  email + password  ->  users table (bcrypt check)  ->  staff_members (role, active)
       ->  token + role + home_path  ->  the UI redirects to home_path:
           COORDINATOR -> /coordinator/dashboard,  REVIEWER -> /reviewer/queue
"""
import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import HOME_PATHS, CurrentUser, create_access_token, get_current_user, verify_password
from app.core.errors import UnauthorizedError
from app.core.logging_config import log_event
from app.db.session import get_db
from app.repositories import user_repo
from app.schemas.auth import LoginIn, LoginOut, MeOut

router = APIRouter(prefix="/api/auth", tags=["Auth"])
logger = logging.getLogger("app.auth")

LOGIN_FAILED = "Email or password is incorrect"


@router.post("/login", response_model=LoginOut)
def login(body: LoginIn, db: Session = Depends(get_db)) -> LoginOut:
    user = user_repo.get_by_email(db, body.email)
    password_ok = verify_password(body.password, user.password_hash if user else None)

    if user is None or not password_ok or not user.staff.active:
        # One message for every failure, so the form never reveals which emails exist.
        log_event(logger, "login_failed", logging.WARNING)
        raise UnauthorizedError(LOGIN_FAILED)

    staff = user.staff
    log_event(logger, "login_succeeded", staff_code=staff.staff_code, role=staff.role)
    return LoginOut(
        token=create_access_token(staff),
        staff_code=staff.staff_code,
        role=staff.role,
        display_label=staff.display_label,
        home_path=HOME_PATHS[staff.role],
    )


@router.get("/me", response_model=MeOut)
def me(user: CurrentUser = Depends(get_current_user)) -> MeOut:
    """The UI calls this after a page refresh to confirm the session and the role."""
    return MeOut(staff_code=user.staff_code, role=user.role,
                 display_label=user.display_label, home_path=user.home_path)