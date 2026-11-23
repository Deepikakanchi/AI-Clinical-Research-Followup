"""Dashboard, follow-ups and review queue.  (US-14, US-22, US-26, US-28, US-29)

GET /api/staff and GET /api/audit-events live in Person 1's routers.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.repositories import visit_repo
from app.schemas.report import FollowUpItems, FollowUpReport, ReviewQueueItem

router = APIRouter(prefix="/api", tags=["Dashboard"])


@router.get("/reports/follow-ups", response_model=FollowUpReport, responses={401: {}},
            summary="Your due, overdue, completed, missed and awaiting-review counts (SQL)")
def follow_up_report(study_id: int | None = Query(None, gt=0), db: Session = Depends(get_db),
                     user: CurrentUser = Depends(get_current_user)):
    return visit_repo.follow_up_report(db, user, get_settings().due_window_days, study_id)


@router.get("/reports/follow-up-items", response_model=FollowUpItems, responses={401: {}},
            summary="Missed and overdue visits, notes with actions and flagged summaries, by date (no AI)")
def follow_up_items(study_id: int | None = Query(None, gt=0), db: Session = Depends(get_db),
                    user: CurrentUser = Depends(get_current_user)):
    return {
        "missed_or_overdue_visits": visit_repo.list_visits(db, user, get_settings().due_window_days,
                                                           study_id=study_id, view="follow_up"),
        "notes_with_actions": visit_repo.notes_with_actions(db, user, study_id),
        "flagged_summaries": visit_repo.flagged_summaries(db, user, study_id),
    }


@router.get("/review-queue", response_model=list[ReviewQueueItem], responses={401: {}},
            summary="AI drafts awaiting review for your participants")
def review_queue(study_id: int | None = Query(None, gt=0), db: Session = Depends(get_db),
                 user: CurrentUser = Depends(get_current_user)):
    return visit_repo.review_queue(db, user, study_id)