"""
schemas/auth.py - Pydantic models for login, owned by Rajnish Maurya.

LoginIn (email + password), LoginOut (token, role, home_path) and MeOut.
Used by routers/auth.py.
"""

from pydantic import BaseModel, Field, field_validator

EMAIL_PATTERN = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class LoginIn(BaseModel):
    email: str = Field(max_length=254, pattern=EMAIL_PATTERN, examples=["coord01@study.test"])
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email", mode="before")
    @classmethod
    def normalise_email(cls, value):
        return value.strip().lower() if isinstance(value, str) else value


class LoginOut(BaseModel):
    token: str
    token_type: str = "bearer"
    staff_code: str
    role: str
    display_label: str
    home_path: str = Field(description="Where the UI should redirect after login")


class MeOut(BaseModel):
    staff_code: str
    role: str
    display_label: str
    home_path: str