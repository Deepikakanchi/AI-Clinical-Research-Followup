"""Visits.  (US-10 to US-14)"""
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.auth import COORDINATOR, CurrentUser, get_current_user, require_role
from app.core.config import get_settings
from app.db.session import get_db
from app.repositories import visit_repo
from app.schemas.visit import VisitCreate, VisitDetail, VisitOut, VisitStatus, VisitUpdate
from app.services import visit_service

router = APIRouter(prefix="/api/visits", tags=["Visits"])


@router.post("", response_model=VisitOut, status_code=status.HTTP_201_CREATED,
             responses={401: {}, 403: {}, 404: {}, 409: {"description": "Withdrawn consent or duplicate time"}, 422: {}},
             summary="Schedule a visit (coordinator)")
def schedule(data: VisitCreate, db: Session = Depends(get_db),
             user: CurrentUser = Depends(require_role(COORDINATOR))):
    return visit_service.schedule(db, user, data)


@router.get("", response_model=list[VisitOut], summary="List your visits with filters (done in SQL)")
def list_visits(
    study_id: int | None = Query(None, gt=0),
    participant_id: int | None = Query(None, gt=0),
    status_: VisitStatus | None = Query(None, alias="status"),
    date_from: datetime | None = Query(None, alias="from"),
    date_to: datetime | None = Query(None, alias="to"),
    view: Literal["all", "upcoming", "due", "overdue", "follow_up"] = "all",
    db: Session = Depends(get_db),
    user: CurrentUser = Depends(get_current_user),
):
    return visit_repo.list_visits(db, user, get_settings().due_window_days, study_id=study_id,
                                  participant_id=participant_id, status=status_,
                                  date_from=date_from, date_to=date_to, view=view)


@router.get("/{visit_id}", response_model=VisitDetail, responses={401: {}, 404: {}},
            summary="Visit with notes and AI draft state")
def get_visit(visit_id: int, db: Session = Depends(get_db), user: CurrentUser = Depends(get_current_user)):
    return visit_service.visit_detail(db, user, visit_id)


@router.patch("/{visit_id}", response_model=VisitOut,
              responses={401: {}, 403: {}, 404: {}, 409: {"description": "Rule or clashing visit"}, 422: {}},
              summary="Reschedule or change status (coordinator)")
def update(visit_id: int, data: VisitUpdate, db: Session = Depends(get_db),
           user: CurrentUser = Depends(require_role(COORDINATOR))):
    return visit_service.update(db, user, visit_id, data)