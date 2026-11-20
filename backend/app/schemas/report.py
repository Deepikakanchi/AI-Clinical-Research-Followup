"""Dashboard, review queue, staff and audit schemas.  (US-22, US-27, US-28, US-30)"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.visit import VisitOut


class StaffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    staff_code: str
    display_label: str
    role: str


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


class AuditOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    event_id: int
    entity_type: str
    entity_id: int
    action: str
    actor_code: str
    old_value: str | None
    new_value: str | None
    created_at: datetime