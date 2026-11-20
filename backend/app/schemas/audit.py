from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict

EntityType = Literal["study", "participant", "visit", "note", "summary", "review"]


class AuditEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    event_id: int
    entity_type: EntityType
    entity_id: int
    action: str
    actor_code: str
    old_value: str | None
    new_value: str | None
    created_at: datetime