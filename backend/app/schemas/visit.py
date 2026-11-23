"""Visit schemas.  (US-10 to US-13)"""
from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator, model_validator

from app.schemas.note import NoteOut

VisitType = Literal["BASELINE", "FOLLOW_UP", "CLOSE_OUT"]
VisitStatus = Literal["SCHEDULED", "COMPLETED", "MISSED", "CANCELLED"]
DueLabel = Literal["DUE", "OVERDUE"]
DraftState = Literal["NO_NOTES", "NOT_REQUESTED", "DRAFT_UNAVAILABLE", "AWAITING_REVIEW", "APPROVED", "REJECTED"]
CoordinatorCode = Annotated[str, StringConstraints(strip_whitespace=True, pattern=r"^COORD-\d{2}$")]


def _future(value: datetime) -> datetime:
    value = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if value < datetime.now(timezone.utc):
        raise ValueError("Visit date cannot be in the past")
    return value


class VisitCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [
        {"participant_id": 1, "scheduled_for": "2026-12-15T10:00:00Z", "visit_type": "FOLLOW_UP"}]})
    participant_id: int = Field(gt=0)
    scheduled_for: datetime
    visit_type: VisitType
    coordinator_code: CoordinatorCode | None = Field(
        None, description="Defaults to the participant's coordinator")

    @field_validator("scheduled_for")
    @classmethod
    def not_in_past(cls, value: datetime) -> datetime:
        return _future(value)


class VisitUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"status": "COMPLETED"}]})
    scheduled_for: datetime | None = None
    status: VisitStatus | None = None

    @field_validator("scheduled_for")
    @classmethod
    def not_in_past(cls, value: datetime | None) -> datetime | None:
        return None if value is None else _future(value)

    @model_validator(mode="after")
    def at_least_one(self):
        if self.scheduled_for is None and self.status is None:
            raise ValueError("Provide scheduled_for or status")
        return self


class VisitOut(BaseModel):
    visit_id: int
    participant_id: int
    participant_code: str
    study_id: int
    study_code: str
    scheduled_for: datetime
    visit_type: str
    status: str
    coordinator_code: str
    due_label: DueLabel | None = Field(None, description="Calculated in SQL: DUE within the window, OVERDUE if past")


class LatestSummaryOut(BaseModel):
    summary_id: int
    generation_status: str
    error_code: str | None
    created_at: datetime
    review_decision: str | None


class VisitDetail(VisitOut):
    notes: list[NoteOut]
    draft_state: DraftState
    latest_summary: LatestSummaryOut | None