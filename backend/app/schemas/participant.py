from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

ConsentStatus = Literal["ACTIVE", "WITHDRAWN"]


class ParticipantCreate(BaseModel):
    """participant_code and coordinator_code are NOT accepted: the backend sets both.
    Unknown fields are ignored, so an old client sending them cannot override anything."""
    model_config = ConfigDict(extra="ignore")

    study_id: int = Field(gt=0)
    consent_status: ConsentStatus
    reviewer_code: str = Field(pattern=r"^REV-\d{2}$", examples=["REV-01"])


class ConsentUpdate(BaseModel):
    consent_status: ConsentStatus
    # Accepted for the UI but deliberately NOT stored: free text could hold personal data.
    reason: str | None = Field(default=None, max_length=300)


class ParticipantOut(BaseModel):
    participant_id: int
    study_id: int
    study_code: str
    participant_code: str
    consent_status: ConsentStatus
    coordinator_code: str
    reviewer_code: str
    enrolled_at: datetime
    consent_updated_at: datetime


class ParticipantVisit(BaseModel):
    """Light visit row for the profile page. Person 2's VisitOut adds due_label and
    allowed_status_changes; swap this for VisitOut once visit_service is merged."""
    model_config = ConfigDict(from_attributes=True)

    visit_id: int
    scheduled_for: datetime
    visit_type: str
    status: str
    coordinator_code: str


class ParticipantDetail(ParticipantOut):
    visits: list[ParticipantVisit] = Field(description="Newest first")