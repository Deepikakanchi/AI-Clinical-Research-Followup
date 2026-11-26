"""Visit note schemas.  (US-15, US-16)

Workflow (v2): a note holds OBSERVATIONS only, up to 16,000 characters (about 4,000 tokens).
Follow-up actions are proposed by the AI draft and decided by the reviewer.
NoteOut still returns follow_up_actions so that older notes display correctly.
"""
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

MAX_OBSERVATION_CHARS = 16000   # about 4,000 tokens (roughly 4 characters per token)


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{
        "observation_text": "Follow-up visit completed. The participant returned the sleep diary with all entries filled in."}]})
    observation_text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=20,
                                                       max_length=MAX_OBSERVATION_CHARS)]


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    note_id: int
    visit_id: int
    observation_text: str
    follow_up_actions: list[str] = Field(default_factory=list)   # older notes only
    created_at: datetime
    author_code: str