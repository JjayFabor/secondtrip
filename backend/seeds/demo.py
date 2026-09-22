"""Install the deterministic, fictional HVAC demo tenant through the real importer."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.composition import build_storage_provider
from app.core.security import verify_password
from app.core.settings import Settings
from app.db.engine import build_engine, build_session_factory
from app.db.session import tenant_session
from app.modules.identity.models import User, UserCredentials
from app.modules.imports.models import ImportBatch, ImportRow, ImportStatus
from app.modules.jobs.models import Job
from app.modules.organizations.models import Organization, OrganizationMembership
from seeds.hvac import FIXTURE_VERSION, MAPPING, demo_rows, render_csv
from seeds.runtime import (
    SeedPrincipal,
    build_owner_engine,
    ensure_local,
    ensure_principal,
    remove_principal,
    run_import,
)

DEMO_EMAIL = "hvac-demo@secondtrip.dev"
DEMO_SLUG = "secondtrip-hvac-demo"
DEMO_NAME = "SecondTrip HVAC Demo"
MANIFEST_PATH = Path(__file__).parent / "data" / "hvac_demo_expectations.json"


@dataclass(frozen=True, slots=True)
class ExistingDemo:
    principal: SeedPrincipal
    password_matches: bool


def _manifest() -> dict[str, object]:
    value = cast(dict[str, object], json.loads(MANIFEST_PATH.read_text()))
    if value.get("fixture_version") != FIXTURE_VERSION:
        raise RuntimeError("Demo expectation manifest does not match the fixture version.")
    return value


async def _find_existing(
    owner_factory: async_sessionmaker[AsyncSession], password: str
) -> ExistingDemo | None:
    async with owner_factory() as session:
        user = await session.scalar(
            select(User).where(User.email == DEMO_EMAIL, User.deleted_at.is_(None))
        )
        organization = await session.scalar(
            select(Organization).where(Organization.slug == DEMO_SLUG)
        )
        if user is None and organization is None:
            return None
        if user is None or organization is None:
            raise RuntimeError(
                "Reserved demo email/slug is only partially present; inspect it manually."
            )
        if organization.name != DEMO_NAME or organization.industry_key != "hvac":
            raise RuntimeError(
                "Reserved demo slug belongs to an unexpected organization; refusing cleanup."
            )
        memberships = list(
            (
                await session.execute(
                    select(OrganizationMembership).where(
                        OrganizationMembership.user_id == user.id,
                        OrganizationMembership.revoked_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        if len(memberships) != 1 or memberships[0].organization_id != organization.id:
            raise RuntimeError("Reserved demo user has non-demo memberships; refusing cleanup.")
        credentials = await session.get(UserCredentials, user.id)
        return ExistingDemo(
            principal=SeedPrincipal(user.id, organization.id),
            password_matches=(
                credentials is not None and verify_password(credentials.password_hash, password)
            ),
        )


def _expected_external_ids(manifest: dict[str, object]) -> set[str]:
    pairs = manifest.get("pairs")
    if not isinstance(pairs, list):
        raise RuntimeError("Demo expectation manifest has no pair list.")
    external_ids = {
        str(identifier)
        for pair in pairs
        if isinstance(pair, dict)
        for identifier in pair.get("external_job_ids", [])
    }
    external_ids.update(f"DEMO-NOISE-{index:02d}" for index in range(1, 33))
    return external_ids


async def _is_current(
    settings: Settings,
    existing: ExistingDemo,
    *,
    fixture_sha256: str,
    expected_external_ids: set[str],
) -> bool:
    if not existing.password_matches:
        return False
    engine = build_engine(settings)
    factory = build_session_factory(engine)
    try:
        async with tenant_session(factory, existing.principal.tenant("seed-demo:check")) as session:
            batch = await session.scalar(
                select(ImportBatch)
                .where(
                    ImportBatch.file_sha256 == bytes.fromhex(fixture_sha256),
                    ImportBatch.status == ImportStatus.COMPLETED,
                    ImportBatch.deleted_at.is_(None),
                )
                .order_by(ImportBatch.created_at.desc())
                .limit(1)
            )
            if batch is None or batch.total_rows != len(expected_external_ids):
                return False
            jobs = set(
                (
                    await session.execute(select(Job.external_id).where(Job.deleted_at.is_(None)))
                ).scalars()
            )
            import_rows = await session.scalar(
                select(func.count())
                .select_from(ImportRow)
                .where(ImportRow.import_batch_id == batch.id)
            )
            return jobs == expected_external_ids and int(import_rows or 0) == len(
                expected_external_ids
            )
    finally:
        await engine.dispose()


async def _verify_import(
    settings: Settings,
    principal: SeedPrincipal,
    *,
    fixture_sha256: str,
    expected_external_ids: set[str],
) -> None:
    existing = ExistingDemo(principal=principal, password_matches=True)
    if not await _is_current(
        settings,
        existing,
        fixture_sha256=fixture_sha256,
        expected_external_ids=expected_external_ids,
    ):
        raise RuntimeError("Demo import completed but its manifest/count verification failed.")


async def execute() -> int:
    settings = Settings()
    ensure_local(settings)
    if settings.storage_provider != "local":
        raise RuntimeError("The persistent demo seed requires STORAGE_PROVIDER=local.")
    password = settings.demo_password
    if len(password) < 12:
        raise RuntimeError("DEMO_PASSWORD must contain at least 12 characters.")
    force_reset = settings.demo_reset
    manifest = _manifest()
    fixture = render_csv(demo_rows())
    expected_external_ids = _expected_external_ids(manifest)
    if fixture.rows != 96 or len(expected_external_ids) != fixture.rows:
        raise RuntimeError("Demo fixture and expectation manifest cardinalities differ.")

    storage = build_storage_provider(settings)
    owner_engine = build_owner_engine(settings)
    owner_factory = async_sessionmaker(owner_engine, expire_on_commit=False)
    try:
        existing = await _find_existing(owner_factory, password)
        if (
            existing is not None
            and not force_reset
            and await _is_current(
                settings,
                existing,
                fixture_sha256=fixture.sha256,
                expected_external_ids=expected_external_ids,
            )
        ):
            print(
                f"Demo is current (no changes): org={existing.principal.organization_id} "
                f"version={FIXTURE_VERSION} jobs={fixture.rows}"
            )
            print(f"Open {settings.frontend_url}/login and sign in as {DEMO_EMAIL}.")
            return 0

        if existing is not None:
            await storage.delete_prefix(f"orgs/{existing.principal.organization_id}")
            await remove_principal(owner_factory, existing.principal)

        principal = await ensure_principal(
            owner_factory,
            settings,
            email=DEMO_EMAIL,
            password=password,
            organization_name=DEMO_NAME,
            organization_slug=DEMO_SLUG,
            plan_key="pro",
        )
        run = await run_import(
            settings,
            principal,
            storage,
            fixture.body,
            MAPPING,
            original_filename=f"secondtrip-demo-{FIXTURE_VERSION}.csv",
            timeout=300,
        )
        if run.created_jobs != fixture.rows or run.error_rows or run.skipped_rows:
            raise RuntimeError("Demo import did not produce the expected clean 96-job result.")
        await _verify_import(
            settings,
            principal,
            fixture_sha256=fixture.sha256,
            expected_external_ids=expected_external_ids,
        )
        print(
            f"Demo seeded: org={principal.organization_id} version={FIXTURE_VERSION} "
            f"jobs={fixture.rows} sha256={fixture.sha256}"
        )
        print("Scenarios: 12 callbacks, 8 maintenance, 4 planned multi-visit, 8 unrelated.")
        print(f"Open {settings.frontend_url}/login and sign in as {DEMO_EMAIL}.")
        return 0
    finally:
        await owner_engine.dispose()


def main() -> None:
    raise SystemExit(asyncio.run(execute()))


if __name__ == "__main__":
    main()
