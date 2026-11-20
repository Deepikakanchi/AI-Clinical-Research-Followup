"""Visit note schemas.  (US-15, US-16)"""
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

Action = Annotated[str, StringConstraints(strip_whitespace=True, min_length=3, max_length=200)]


class NoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={"examples": [{
        "observation_text": "Participant returned the sleep diary for all 7 days. Device data synced.",
        "follow_up_actions": ["Book next follow-up visit"]}]})
    observation_text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=20, max_length=4000)]
    follow_up_actions: list[Action] = Field(default_factory=list, max_length=10)


class NoteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    note_id: int
    visit_id: int
    observation_text: str
    follow_up_actions: list[str]
    created_at: datetime
    author_code: str