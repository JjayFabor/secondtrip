"""Assembles every module's router under /api/v1. See
docs/architecture/15-api-design.md §1 — /health and /ready are the only
routes that live outside this prefix (wired directly in app/main.py).
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.local_storage import router as local_storage_router
from app.modules.detection.router import router as detection_router
from app.modules.identity.router import me_router as identity_me_router
from app.modules.identity.router import router as identity_router
from app.modules.imports.router import router as imports_router
from app.modules.organizations.router import invitations_router, me_org_router, orgs_router

api_v1_router = APIRouter(prefix="/api/v1")
api_v1_router.include_router(identity_router)
api_v1_router.include_router(identity_me_router)
api_v1_router.include_router(orgs_router)
api_v1_router.include_router(invitations_router)
api_v1_router.include_router(me_org_router)
api_v1_router.include_router(imports_router)
api_v1_router.include_router(detection_router)
api_v1_router.include_router(local_storage_router)
