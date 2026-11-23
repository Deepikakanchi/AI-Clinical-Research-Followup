"""FastAPI application: settings, logging, CORS, error handlers and routers.

Run from the backend folder:  uvicorn app.main:app --reload
Swagger UI:                    http://localhost:8000/docs
"""
import logging
import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging_config import log_event, setup_logging
from app.db.session import get_sessionmaker
from app.routers import audit, auth, notes, participants, reports, staff, studies, visits

# Person 2 adds:  from app.routers import notes, reports, visits
# Person 3 adds:  from app.routers import summaries

logger = logging.getLogger("app.http")


def create_app() -> FastAPI:
    settings = get_settings()            # stops here with a clear error if .env is incomplete
    setup_logging(settings.log_level)

    app = FastAPI(
        title="Clinical Research Follow-up API",
        version="1.0.0",
        description="Synthetic data only. AI output is a draft, never a clinical decision.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH"],
        allow_headers=["Authorization", "Content-Type"],
    )
    register_exception_handlers(app)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        started = time.perf_counter()
        response = await call_next(request)
        log_event(logger, "http_request", method=request.method, path=request.url.path,
                  status=response.status_code,
                  duration_ms=round((time.perf_counter() - started) * 1000, 1))
        return response

    for module in (auth, staff, studies, participants, audit, visits, notes, reports):
        app.include_router(module.router)
    # Person 2: app.include_router(visits.router); app.include_router(notes.router); app.include_router(reports.router)
    # Person 3: app.include_router(summaries.router)

    @app.get("/api/health", tags=["Health"])
    def health():
        try:
            with get_sessionmaker()() as db:
                db.execute(text("SELECT 1"))
            database = "up"
        except Exception:
            database = "down"
        return {"status": "ok" if database == "up" else "degraded",
                "database": database, "ai_enabled": settings.ai_enabled}

    return app


app = create_app()