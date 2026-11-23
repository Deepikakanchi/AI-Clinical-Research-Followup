"""
schemas/study.py - Pydantic models for studies, owned by Rajnish Maurya .  (US-06)

StudyCreate (request) and StudyOut (response). Used by routers/studies.py.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

StudyType = Literal["OBSERVATIONAL", "REGISTRY"]


class StudyCreate(BaseModel):
    study_code: str = Field(pattern=r"^STD-[A-Z0-9-]{3,20}$", examples=["STD-DIA-03"])
    title: str = Field(min_length=5, max_length=150)
    study_type: StudyType
    active: bool = True

    @field_validator("study_code", "title", mode="before")
    @classmethod
    def strip(cls, value):
        return value.strip() if isinstance(value, str) else value


class StudyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    study_id: int
    study_code: str
    title: str
    study_type: StudyType
    active: bool
    created_at: datetime