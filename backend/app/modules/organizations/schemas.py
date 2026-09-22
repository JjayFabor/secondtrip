from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.core.permissions import OrganizationRole


class CreateOrganizationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)


class OrganizationOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: UUID
    name: str
    slug: str
    timezone: str
    currency_code: str
    status: str


class MyOrganizationOut(OrganizationOut):
    role: OrganizationRole


class MembershipOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: UUID
    user_id: UUID
    role: OrganizationRole
    joined_at: datetime


class ChangeRoleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: OrganizationRole


class TransferOwnershipRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    to_user_id: UUID


class InviteMemberRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: EmailStr
    role: OrganizationRole

    @field_validator("email")
    @classmethod
    def _lowercase_email(cls, v: str) -> str:
        return v.lower()

    @field_validator("role")
    @classmethod
    def _no_owner_invite(cls, v: OrganizationRole) -> OrganizationRole:
        if v is OrganizationRole.OWNER:
            raise ValueError("Cannot invite directly as owner — transfer ownership instead.")
        return v


class InvitationOut(BaseModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)
    id: UUID
    email: str
    role: OrganizationRole
    expires_at: datetime
    created_at: datetime


class InvitationPreviewOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    organization_name: str
    role: OrganizationRole
    email: str


class MyInvitationOut(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    organization_id: UUID
    organization_name: str
    email: str
    role: OrganizationRole
    expires_at: datetime


class AcceptInvitationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str
