"""Domain errors and the handlers that turn them into HTTP responses.

Services raise these; routers never build error responses by hand.
Every error body has a "detail" field, matching openapi.yaml.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

from app.core.logging_config import log_event

logger = logging.getLogger("app.errors")


class AppError(Exception):
    status_code = 400

    def __init__(self, detail, **extra):
        super().__init__(detail if isinstance(detail, str) else "validation error")
        self.detail = detail
        self.extra = extra


class UnauthorizedError(AppError):
    status_code = 401


class ForbiddenError(AppError):
    status_code = 403


class NotFoundError(AppError):
    """Also used for records outside the caller's scope, so their existence is not revealed."""
    status_code = 404


class ConflictError(AppError):
    status_code = 409


class FieldValidationError(AppError):
    """A 422 in FastAPI's own format, so the UI shows it beside the field."""
    status_code = 422

    def __init__(self, field: str, message: str, location: str = "body"):
        super().__init__([{"loc": [location, field], "msg": message, "type": "value_error"}])


class DraftUnavailableError(AppError):
    """For Person 3: 502 invalid output / content filter, 503 unavailable, 504 timeout."""

    def __init__(self, status_code: int, error_code: str):
        super().__init__("Draft unavailable, try again later")
        self.status_code = status_code
        self.error_code = error_code


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError):
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail, **exc.extra},
            headers=headers,
        )

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(request: Request, exc: IntegrityError):
        # Log only the constraint name, never the parameters (they may hold text).
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        log_event(logger, "db_integrity_error", logging.WARNING,
                  path=request.url.path, constraint=constraint)
        return JSONResponse(status_code=409,
                            content={"detail": "This change conflicts with existing data"})

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception):
        log_event(logger, "unhandled_error", logging.ERROR,
                  path=request.url.path, exception_type=type(exc).__name__)
        return JSONResponse(status_code=500, content={"detail": "Unexpected server error"})