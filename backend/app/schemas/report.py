"""Dashboard, follow-up and review-queue schemas.  (US-14, US-22, US-26, US-28, US-29)

Workflow (v2): open follow-up actions are the reviewer's final actions on APPROVED
summaries (notes no longer hold actions).
"""
from datetime import datetime

from pydantic import BaseModel

from app.schemas.visit import VisitOut


class FollowUpReport(BaseModel):
    active_participants: int
    scheduled: int
    due_7_days: int
    overdue: int
    completed: int
    missed: int
    cancelled: int
    open_follow_up_actions: int
    awaiting_review: int


class ReviewQueueItem(BaseModel):
    summary_id: int
    visit_id: int
    visit_date: datetime
    participant_code: str
    study_code: str
    created_at: datetime
    review_state: str


class ApprovedActionItem(BaseModel):
    """Follow-up actions confirmed by the reviewer on an approved summary."""
    review_id: int
    summary_id: int
    visit_id: int
    participant_code: str
    study_code: str
    reviewer_code: str
    reviewed_at: datetime
    follow_up_actions: list[str]


class FlaggedSummaryItem(BaseModel):
    summary_id: int
    visit_id: int
    participant_code: str
    study_code: str
    reviewer_code: str
    reviewed_at: datetime


class FollowUpItems(BaseModel):
    missed_or_overdue_visits: list[VisitOut]
    approved_actions: list[ApprovedActionItem]
    flagged_summaries: list[FlaggedSummaryItem]