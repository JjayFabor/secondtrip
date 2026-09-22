"""Typed job-handler registry; workers never dispatch by import path."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pydantic import BaseModel

from app.core.tenancy import TenantContext
from app.modules.tasks.control import JobControl

JobHandler = Callable[[TenantContext, BaseModel, JobControl], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class HandlerDefinition:
    payload_model: type[BaseModel]
    handler: JobHandler
    timeout_seconds: float


class JobRegistry:
    def __init__(self) -> None:
        self._definitions: dict[str, HandlerDefinition] = {}

    def register(
        self,
        job_type: str,
        *,
        payload_model: type[BaseModel],
        handler: JobHandler,
        timeout_seconds: float,
    ) -> None:
        if job_type in self._definitions:
            raise ValueError(f"Job type already registered: {job_type}")
        self._definitions[job_type] = HandlerDefinition(
            payload_model=payload_model,
            handler=handler,
            timeout_seconds=timeout_seconds,
        )

    def get(self, job_type: str) -> HandlerDefinition | None:
        return self._definitions.get(job_type)
