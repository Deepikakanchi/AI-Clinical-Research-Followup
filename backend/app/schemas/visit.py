"""Visit schemas.  (US-10 to US-13)"""
from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import DueLabel, StaffCode, VisitStatus, VisitType


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class VisitCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [
        {"participant_id": 1, "scheduled_for": "2026-12-15T10:00:00Z", "visit_type": "FOLLOW_UP", "coordinator_code": "COORD-01"}]})
    participant_id: int = Field(gt=0)
    scheduled_for: datetime
    visit_type: VisitType
    coordinator_code: StaffCode

    @field_validator("scheduled_for")
    @classmethod
    def not_in_past(cls, value: datetime) -> datetime:
        value = _aware(value)
        if value < datetime.now(timezone.utc):
            raise ValueError("Visit date cannot be in the past")
        return value


class VisitUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{"status": "COMPLETED"}]})
    scheduled_for: datetime | None = None
    status: VisitStatus | None = None
    coordinator_code: StaffCode | None = None

    @field_validator("scheduled_for")
    @classmethod
    def not_in_past(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        value = _aware(value)
        if value < datetime.now(timezone.utc):
            raise ValueError("Visit date cannot be in the past")
        return value

    @model_validator(mode="after")
    def at_least_one(self):
        if self.scheduled_for is None and self.status is None and self.coordinator_code is None:
            raise ValueError("Provide scheduled_for, status or coordinator_code")
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