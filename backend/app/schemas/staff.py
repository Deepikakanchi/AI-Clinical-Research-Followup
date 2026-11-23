"""
schemas/staff.py - Pydantic model for staff in API responses, owned by Rajnish Maurya.
Never includes login details (email, password hash).

Used by routers/staff.py.
"""
from pydantic import BaseModel, ConfigDict


class StaffOut(BaseModel):
    """No login details (email, password hash) are ever returned."""
    model_config = ConfigDict(from_attributes=True)

    staff_code: str
    display_label: str
    role: str
    active: bool