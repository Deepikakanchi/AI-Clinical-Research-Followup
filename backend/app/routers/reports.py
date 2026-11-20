"""Dashboard, follow-ups, staff and audit.  (US-14, US-26 to US-30)"""
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.auth import current_staff
from app.core.config import settings
from app.db.session import get_db
from app.repositories import audit_repo, staff_repo, summary_repo, visit_repo
from app.schemas.report import AuditOut, FollowUpItems, FollowUpReport, StaffOut

router = APIRouter(prefix="/api", tags=["Dashboard and audit"], dependencies=[Depends(current_staff)])


@router.get("/reports/follow-ups", response_model=FollowUpReport,
            summary="Due, overdue, completed, missed and awaiting-review counts (SQL)")
def follow_up_report(study_id: int | None = Query(None, gt=0), db: Session = Depends(get_db)):
    return visit_repo.follow_up_report(db, settings.due_window_days, study_id)


@router.get("/reports/follow-up-items", response_model=FollowUpItems,
            summary="Missed and overdue visits, open actions and flagged summaries, by date (no AI)")
def follow_up_items(study_id: int | None = Query(None, gt=0), db: Session = Depends(get_db)):
    return {
        "missed_or_overdue_visits": visit_repo.list_visits(db, settings.due_window_days, study_id=study_id,
                                                           view="follow_up"),
        "notes_with_actions": visit_repo.notes_with_actions(db, study_id),
        "flagged_summaries": summary_repo.flagged_summaries(db, study_id),
    }


@router.get("/staff", response_model=list[StaffOut], tags=["Staff"], summary="Fictional staff for the selector")
def list_staff(db: Session = Depends(get_db)):
    return staff_repo.list_active(db)


@router.get("/audit-events", response_model=list[AuditOut], summary="Audit trail by entity, in time order")
def audit_events(entity_type: Literal["study", "participant", "visit", "note", "summary", "review"] | None = None,
                 entity_id: int | None = Query(None, gt=0), db: Session = Depends(get_db)):
    return audit_repo.list_events(db, entity_type, entity_id)