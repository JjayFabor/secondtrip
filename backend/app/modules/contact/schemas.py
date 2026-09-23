"""Strict public-contact request and response schemas."""

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class ContactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=120)
    email: EmailStr
    company: str | None = Field(default=None, max_length=160)
    subject: str = Field(min_length=1, max_length=160)
    message: str = Field(min_length=10, max_length=5000)
    website: str = Field(default="", max_length=240)


class ContactResponse(BaseModel):
    detail: str
