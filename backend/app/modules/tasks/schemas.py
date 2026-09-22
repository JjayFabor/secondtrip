"""Versioned payload schemas for registered background jobs."""

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, field_validator

from app.providers.storage.keys import validate_storage_key


class StorageCleanupPayload(BaseModel):
    key: str

    @field_validator("key")
    @classmethod
    def _key_is_server_owned(cls, value: str) -> str:
        return validate_storage_key(value)


class ImportProfilePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    batch_id: UUID


class ImportValidatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    batch_id: UUID


class ImportErrorReportPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    batch_id: UUID


class ImportProcessPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    batch_id: UUID


class DetectionRunPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: Literal[1]
    detection_run_id: UUID
