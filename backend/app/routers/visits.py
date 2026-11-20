"""Visits.  (US-10 to US-14)"""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.auth import COORDINATOR, current_staff, require_role
from app.core.config import settings
from app.db.models import StaffMember
from app.db.session import get_db
from app.repositories import note_repo, summary_repo, visit_repo
from app.schemas.common import VisitStatus
from app.schemas.note import NoteOut
from app.schemas.summary import SummaryOut
from app.schemas.visit import VisitCreate, VisitOut, VisitUpdate
from app.services import summary_service, visit_service
from pydantic import BaseModel

router = APIRouter(prefix="/api/visits", tags=["Visits"], dependencies=[Depends(current_staff)])


class VisitDetail(VisitOut):
    notes: list[NoteOut]
    draft_state: Literal["NO_NOTES", "NOT_REQUESTED", "DRAFT_UNAVAILABLE", "AWAITING_REVIEW", "APPROVED", "REJECTED"]
    latest_summary: SummaryOut | None


@router.post("", response_model=VisitOut, status_code=status.HTTP_201_CREATED,
             responses={401: {}, 403: {}, 404: {}, 409: {"description": "Withdrawn consent or duplicate time"}, 422: {}},
             summary="Schedule a visit (coordinator)")
def schedule(data: VisitCreate, db: Session = Depends(get_db),
             staff: StaffMember = Depends(require_role(COORDINATOR))):
    return visit_service.schedule(db, data, staff)


@router.get("", response_model=list[VisitOut], summary="List visits with filters (done in SQL)")
def list_visits(
    study_id: int | None = Query(None, gt=0),
    participant_id: int | None = Query(None, gt=0),
    status_: VisitStatus | None = Query(None, alias="status"),
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    view: Literal["all", "upcoming", "due", "overdue", "follow_up"] = "all",
    db: Session = Depends(get_db),
):
    return visit_repo.list_visits(db, settings.due_window_days, study_id=study_id, participant_id=participant_id,
                                  status=status_, date_from=date_from, date_to=date_to, view=view)


@router.get("/{visit_id}", response_model=VisitDetail, responses={404: {}},
            summary="Visit with notes and latest summary state")
def get_visit(visit_id: int, db: Session = Depends(get_db)):
    row = visit_service.visit_row(db, visit_id)
    notes = note_repo.list_for_visit(db, visit_id)
    latest = summary_repo.latest_for_visit(db, visit_id)
    if not notes:
        state = "NO_NOTES"
    elif latest is None:
        state = "NOT_REQUESTED"
    else:
        state = {"FAILED": "DRAFT_UNAVAILABLE"}.get(summary_service.review_state(latest),
                                                    summary_service.review_state(latest))
    return {**row, "notes": notes, "draft_state": state,
            "latest_summary": summary_service.summary_out(latest) if latest else None}


@router.patch("/{visit_id}", response_model=VisitOut,
              responses={401: {}, 403: {}, 404: {}, 409: {"description": "Rule or clashing visit"}, 422: {}},
              summary="Reschedule or change status (coordinator)")
def update(visit_id: int, data: VisitUpdate, db: Session = Depends(get_db),
           staff: StaffMember = Depends(require_role(COORDINATOR))):
    return visit_service.update(db, visit_id, data, staff)