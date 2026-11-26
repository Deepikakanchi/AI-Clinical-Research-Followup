"""Pydantic schemas for AI drafts and reviewer decisions (Person 3 slice).

Workflow (v2):
- The AI drafts up to 5 summary points and proposes up to 3 follow-up actions.
- The reviewer approves (final text + comment + at least one follow-up action,
  which can be edited, removed or added) or rejects (at least one reason, no actions).

SummaryDraft is the contract with the model. Its length limits are enforced
here, in Pydantic, because Azure strict structured outputs reject keywords
such as minLength, maxLength, minItems and maxItems.
"""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

MAX_SUMMARY_POINTS = 5
MAX_AI_ACTIONS = 3
MAX_REVIEW_ACTIONS = 10
MAX_REJECTION_REASONS = 10

SummaryPoint = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=300)]
DraftAction = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=150)]
ReviewerAction = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]
RejectionReason = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=300)]


class SummaryDraft(BaseModel):
    """What the model must return. The model can only ever produce DRAFT."""

    model_config = ConfigDict(extra="forbid")

    summary_points: list[SummaryPoint] = Field(min_length=1, max_length=MAX_SUMMARY_POINTS)
    follow_up_actions: list[DraftAction] = Field(default_factory=list, max_length=MAX_AI_ACTIONS)
    review_status: Literal["DRAFT"]

    @classmethod
    def from_stored(cls, data: dict[str, Any]) -> "SummaryDraft":
        """Read a stored draft. Drafts saved in the older format (visit_summary,
        recorded_observations, ...) are converted so old rows still display."""
        if "summary_points" in data:
            return cls.model_validate(data)
        points = [data.get("visit_summary") or "", *(data.get("recorded_observations") or [])]
        points = [p.strip()[:300] for p in points if p and len(p.strip()) >= 3][:MAX_SUMMARY_POINTS]
        actions = [a.strip()[:150] for a in (data.get("follow_up_actions") or []) if a and len(a.strip()) >= 3]
        return cls(summary_points=points or ["No summary text was stored."],
                   follow_up_actions=actions[:MAX_AI_ACTIONS], review_status="DRAFT")


def _string_list(description: str) -> dict:
    return {"type": "array", "items": {"type": "string"}, "description": description}


# Strict-mode JSON Schema sent as response_format. Every field is required and
# additionalProperties is false, as Azure strict mode demands.
SUMMARY_DRAFT_JSON_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "summary_points": _string_list(
            "Up to 5 short factual points, one sentence each, using only facts stated in the source note."
        ),
        "follow_up_actions": _string_list(
            "At most 3 short administrative next steps for study staff that follow directly from the note."
        ),
        "review_status": {"type": "string", "enum": ["DRAFT"]},
    },
    "required": ["summary_points", "follow_up_actions", "review_status"],
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
    """APPROVED: final text (20-4000) + comment + 1-10 follow-up actions.
    REJECTED: 1-10 reasons; any final text or follow-up actions are dropped."""

    decision: Literal["APPROVED", "REJECTED"]
    final_text: Optional[str] = Field(default=None, max_length=4000)
    reviewer_comment: str = Field(default="", max_length=1000)
    follow_up_actions: list[ReviewerAction] = Field(default_factory=list, max_length=MAX_REVIEW_ACTIONS)
    rejection_reasons: list[RejectionReason] = Field(default_factory=list, max_length=MAX_REJECTION_REASONS)
    follow_up_flag: bool = False

    @model_validator(mode="after")
    def _check_decision_fields(self) -> "ReviewUpdate":
        self.reviewer_comment = self.reviewer_comment.strip()
        if self.decision == "APPROVED":
            if self.final_text is None or len(self.final_text.strip()) < 20:
                raise ValueError("final_text of 20 to 4000 characters is required when approving")
            if not self.reviewer_comment:
                raise ValueError("reviewer_comment is required when approving")
            if not self.follow_up_actions:
                raise ValueError("at least one follow-up action is required when approving")
            self.final_text = self.final_text.strip()
            self.rejection_reasons = []
        else:
            if not self.rejection_reasons:
                raise ValueError("at least one rejection reason is required when rejecting")
            self.final_text = None
            self.follow_up_actions = []
        return self


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    review_id: int
    summary_id: int
    decision: Literal["APPROVED", "REJECTED"]
    final_text: Optional[str] = None
    reviewer_code: str
    reviewer_comment: Optional[str] = None
    final_follow_up_actions: list[str] = Field(default_factory=list)
    rejection_reasons: list[str] = Field(default_factory=list)
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