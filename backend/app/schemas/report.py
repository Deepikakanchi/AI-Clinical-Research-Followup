"""Dashboard, follow-up and review-queue schemas.  (US-14, US-22, US-26, US-28, US-29)"""
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


class NoteActionItem(BaseModel):
    note_id: int
    visit_id: int
    participant_code: str
    study_code: str
    created_at: datetime
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
    notes_with_actions: list[NoteActionItem]
    flagged_summaries: list[FlaggedSummaryItem]