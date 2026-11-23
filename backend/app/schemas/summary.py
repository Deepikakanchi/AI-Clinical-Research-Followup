"""Pydantic schemas for AI drafts and reviewer decisions (Person 3 slice).

SummaryDraft is the contract with the model. Its length limits are enforced
here, in Pydantic, because Azure strict structured outputs reject keywords
such as minLength, maxLength, minItems and maxItems.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

ListItem = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=300)]


class SummaryDraft(BaseModel):
    """What the model must return. The model can only ever produce DRAFT."""

    model_config = ConfigDict(extra="forbid")

    visit_summary: str = Field(min_length=20, max_length=1200)
    recorded_observations: list[ListItem] = Field(default_factory=list, max_length=10)
    follow_up_actions: list[ListItem] = Field(default_factory=list, max_length=10)
    missing_information: list[ListItem] = Field(default_factory=list, max_length=10)
    follow_up_message_draft: Optional[str] = Field(default=None, max_length=600)
    review_status: Literal["DRAFT"]


def _string_list() -> dict:
    return {"type": "array", "items": {"type": "string"}}


# Strict-mode JSON Schema sent as response_format. Every field is required and
# additionalProperties is false, as Azure strict mode demands. The optional
# message is expressed as a nullable string.
SUMMARY_DRAFT_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "visit_summary": {
            "type": "string",
            "description": "2 to 5 factual sentences grounded only in the source note.",
        },
        "recorded_observations": {
            **_string_list(),
            "description": "Observations stated in the note, terms kept exactly as written.",
        },
        "follow_up_actions": {
            **_string_list(),
            "description": "Only actions listed as documented follow-up actions, copied word for word.",
        },
        "missing_information": {
            **_string_list(),
            "description": "Details the note does not state. Never guessed.",
        },
        "follow_up_message_draft": {
            "type": ["string", "null"],
            "description": "Neutral staff-facing note restating documented actions, or null.",
        },
        "review_status": {"type": "string", "enum": ["DRAFT"]},
    },
    "required": [
        "visit_summary",
        "recorded_observations",
        "follow_up_actions",
        "missing_information",
        "follow_up_message_draft",
        "review_status",
    ],
    "additionalProperties": False,
}


# ---------------------------------------------------------------- API schemas

class SummaryOut(BaseModel):
    summary_id: int
    visit_id: int
    draft: Optional[SummaryDraft] = None
    model_id: Optional[str] = None
    deployment_name: Optional[str] = None
    generation_status: Literal["SUCCEEDED", "FAILED"]
    error_code: Optional[str] = None
    latency_ms: Optional[int] = None
    created_at: datetime


class ReviewUpdate(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    final_text: Optional[str] = Field(default=None, max_length=4000)
    reviewer_comment: str = Field(default="", max_length=1000)
    follow_up_flag: bool = False

    @model_validator(mode="after")
    def _check_decision_fields(self) -> "ReviewUpdate":
        if self.decision == "APPROVED":
            if self.final_text is None or len(self.final_text.strip()) < 20:
                raise ValueError("final_text of 20 to 4000 characters is required when approving")
            self.final_text = self.final_text.strip()
        else:
            if not self.reviewer_comment.strip():
                raise ValueError("reviewer_comment is required when rejecting")
            self.final_text = None
        self.reviewer_comment = self.reviewer_comment.strip()
        return self


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    review_id: int
    summary_id: int
    decision: Literal["APPROVED", "REJECTED"]
    final_text: Optional[str] = None
    reviewer_code: str
    reviewer_comment: Optional[str] = None
    follow_up_flag: bool = False
    reviewed_at: datetime


class SourceNoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    note_id: int
    observation_text: str
    follow_up_actions: list[str] = Field(default_factory=list)
    author_code: Optional[str] = None
    created_at: datetime


ReviewState = Literal["AWAITING_REVIEW", "APPROVED", "REJECTED", "DRAFT_UNAVAILABLE"]


class SummaryDetail(BaseModel):
    summary: SummaryOut
    review: Optional[ReviewOut] = None
    source_notes: list[SourceNoteOut]
    review_state: ReviewState


class ReviewQueueItem(BaseModel):
    summary_id: int
    visit_id: int
    visit_date: datetime
    participant_code: str
    study_code: str
    created_at: datetime
    review_state: Literal["AWAITING_REVIEW"] = "AWAITING_REVIEW"