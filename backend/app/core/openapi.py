"""Stable OpenAPI naming shared by schema generation and the live app."""

from __future__ import annotations

from fastapi.routing import APIRoute


def stable_operation_id(route: APIRoute) -> str:
    words = route.name.removesuffix("_endpoint").split("_")
    return words[0] + "".join(word.capitalize() for word in words[1:])
