from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    full_name: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def _lowercase_email(cls, v: str) -> str:
        return v.lower()


class VerifyEmailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str


class ResendVerificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr

    @field_validator("email")
    @classmethod
    def _lowercase_email(cls, v: str) -> str:
        return v.lower()


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    password: str

    @field_validator("email")
    @classmethod
    def _lowercase_email(cls, v: str) -> str:
        return v.lower()


class PasswordResetRequestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr

    @field_validator("email")
    @classmethod
    def _lowercase_email(cls, v: str) -> str:
        return v.lower()


class PasswordResetConfirmRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str
    new_password: str = Field(min_length=12, max_length=128)


class UpdateProfileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    full_name: str | None = Field(default=None, min_length=1, max_length=200)
    timezone: str | None = Field(default=None, max_length=100)


class ChangePasswordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str
    new_password: str = Field(min_length=12, max_length=128)


class EmailChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    new_email: EmailStr

    @field_validator("new_email")
    @classmethod
    def _lowercase_email(cls, v: str) -> str:
        return v.lower()


class ConfirmEmailChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str


class UserOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: UUID
    email: str
    full_name: str
    status: str
    email_verified_at: datetime | None
    timezone: str | None


class SessionOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: UUID
    issued_at: datetime
    expires_at: datetime
    last_seen_at: datetime
    user_agent: str | None


class PendingInvitationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    organization_id: UUID
    organization_name: str
    role: str
    expires_at: datetime
