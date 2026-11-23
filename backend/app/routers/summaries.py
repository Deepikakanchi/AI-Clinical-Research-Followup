"""REST endpoints for AI drafts and reviews.

Person 1 registers this router in main.py:  app.include_router(summaries.router)

Every endpoint needs a signed-in user (Bearer token). Results are limited to the
caller's own participants: a coordinator's by coordinator_code, a reviewer's by
reviewer_code. Anything outside that scope returns 404.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.ai.azure_client import USER_MESSAGE, AIConfig, AIError, SummaryClient
from app.core.auth import CurrentUser, get_current_user, require_role
from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.summary import ReviewOut, ReviewUpdate, SummaryDetail, SummaryOut
from app.services import review_service, summary_service

router = APIRouter(prefix="/api", tags=["AI summaries and review"])


@lru_cache(maxsize=1)
def get_summary_client() -> SummaryClient:
    """One client per process. Tests replace it with app.dependency_overrides."""
    return SummaryClient(AIConfig.from_settings(get_settings()))


@router.post(
    "/visits/{visit_id}/draft-summary",
    response_model=SummaryOut,
    status_code=status.HTTP_201_CREATED,
    responses={401: {}, 403: {}, 404: {}, 409: {}, 502: {}, 503: {}, 504: {}},
)
def create_draft_summary(
    visit_id: int,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role("COORDINATOR", "REVIEWER")),
    client: SummaryClient = Depends(get_summary_client),
) -> SummaryOut:
    try:
        summary = summary_service.generate_draft(db, visit_id, user, client)
    except AIError as err:
        raise HTTPException(status_code=err.status_code, detail=USER_MESSAGE) from None
    return summary_service.to_summary_out(summary)


@router.get("/visits/{visit_id}/summaries", response_model=list[SummaryOut], responses={401: {}, 404: {}})
def list_visit_summaries(
    visit_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> list[SummaryOut]:
    return summary_service.list_visit_summaries(db, visit_id, user)


@router.get("/summaries/{summary_id}", response_model=SummaryDetail, responses={401: {}, 404: {}})
def get_summary(
    summary_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)
) -> SummaryDetail:
    return review_service.get_summary_detail(db, summary_id, user)


@router.patch(
    "/summaries/{summary_id}/review",
    response_model=ReviewOut,
    responses={401: {}, 403: {}, 404: {}, 409: {}, 422: {}},
)
def review_summary(
    summary_id: int,
    payload: ReviewUpdate,
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(require_role("REVIEWER")),
) -> ReviewOut:
    review = review_service.submit_review(db, summary_id, payload, user)
    return ReviewOut.model_validate(review)

