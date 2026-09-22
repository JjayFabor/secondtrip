from collections.abc import Iterator
from typing import Any

from fastapi.routing import APIRoute, APIRouter

from app.api.v1.router import api_v1_router


def _walk_routes(router: APIRouter) -> Iterator[APIRoute]:
    for route in router.routes:
        if hasattr(route, "original_router"):
            yield from _walk_routes(route.original_router)
        elif isinstance(route, APIRoute):
            yield route


def _dependency_names(dependency: Any) -> set[str]:
    names = {getattr(dependency.call, "__name__", "")}
    for child in dependency.dependencies:
        names.update(_dependency_names(child))
    return names


def test_every_org_route_derives_tenant_context_from_its_path() -> None:
    org_routes = [route for route in _walk_routes(api_v1_router) if "/orgs/{org_id}" in route.path]

    assert org_routes
    for route in org_routes:
        assert "require_org_context" in _dependency_names(route.dependant), route.path
