"""Reviewer decisions (Flow E, US-22 to US-26).

The review inserts one summary_reviews row and one audit event in a single
transaction. The ai_summaries row and the visit notes are never touched, so
source, draft and approved text stay separately visible.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser
from app.core.errors import ConflictError, NotFoundError
from app.db.models import SummaryReview
from app.repositories import summary_repo
from app.schemas.summary import (
    ReviewOut,
    ReviewUpdate,
    SourceNoteOut,
    SummaryDetail,
)
from app.services import audit_service
from app.services.summary_service import to_summary_out

ALREADY_REVIEWED_MESSAGE = "This draft has already been reviewed."
NOT_REVIEWABLE_MESSAGE = "Only a successful AI draft can be reviewed."


def submit_review(db: Session, summary_id: int, payload: ReviewUpdate, user: CurrentUser) -> SummaryReview:
    """Role is checked by the router (REVIEWER only). Only the participant's assigned reviewer
    finds the summary; anyone else gets 404."""
    reviewer_code = user.staff_code
    summary = summary_repo.get_owned_summary(db, summary_id, user)
    if summary is None:
        raise NotFoundError(f"Summary {summary_id} not found")
    if summary.generation_status != "SUCCEEDED":
        raise ConflictError(NOT_REVIEWABLE_MESSAGE)
    if summary_repo.get_review_for_summary(db, summary_id) is not None:
        raise ConflictError(ALREADY_REVIEWED_MESSAGE)

    review = summary_repo.insert_review(
        db,
        summary_id=summary_id,
        final_text=payload.final_text,
        decision=payload.decision,
        reviewer_code=reviewer_code,
        reviewer_comment=payload.reviewer_comment or None,
        follow_up_flag=payload.follow_up_flag,
    )
    audit_service.record(db, entity_type="review", entity_id=review.review_id,
                         action=f"REVIEW_{payload.decision}", actor_code=reviewer_code,
                         old_value=None, new_value=payload.decision)
    try:
        db.commit()
    except IntegrityError:
        # Two reviewers submitted at once: the UNIQUE(summary_id) constraint wins.
        db.rollback()
        raise ConflictError(ALREADY_REVIEWED_MESSAGE) from None
    db.refresh(review)
    return review


def _review_state(generation_status: str, review: Optional[SummaryReview]) -> str:
    if generation_status != "SUCCEEDED":
        return "DRAFT_UNAVAILABLE"
    if review is None:
        return "AWAITING_REVIEW"
    return review.decision


def get_summary_detail(db: Session, summary_id: int, user: CurrentUser) -> SummaryDetail:
    summary = summary_repo.get_owned_summary(db, summary_id, user)
    if summary is None:
        raise NotFoundError(f"Summary {summary_id} not found")
    review = summary_repo.get_review_for_summary(db, summary_id)
    notes = summary_repo.get_notes_for_visit(db, summary.visit_id)
    return SummaryDetail(
        summary=to_summary_out(summary),
        review=ReviewOut.model_validate(review) if review else None,
        source_notes=[SourceNoteOut.model_validate(n) for n in notes],
        review_state=_review_state(summary.generation_status, review),
    )


