"""Repeatable local release gate for the 50,000-row import target."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import resource
import statistics
import subprocess
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import cast
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.settings import Settings
from app.providers.storage.local import LocalStorageProvider
from seeds.hvac import MAPPING, performance_rows, render_csv
from seeds.runtime import (
    build_owner_engine,
    ensure_local,
    ensure_principal,
    remove_principal,
    run_import,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=50_000)
    parser.add_argument("--runs", type=int, default=1)
    parser.add_argument("--warmup", type=int, default=1_000)
    parser.add_argument("--max-seconds", type=float, default=120.0)
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--keep-on-failure", action="store_true")
    return parser.parse_args()


async def postgres_version(factory: async_sessionmaker[AsyncSession]) -> str:
    async with factory() as session:
        return str(await session.scalar(text("SHOW server_version")))


def git_revision() -> str | None:
    result = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=Path(__file__).parents[2],
        capture_output=True,
        check=False,
        text=True,
        timeout=2,
    )
    return result.stdout.strip() or None if result.returncode == 0 else None


def total_memory_mib() -> int | None:
    try:
        return int(os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / (1024 * 1024))
    except (OSError, ValueError):
        return None


async def vacuum_import_tables(engine: AsyncEngine) -> None:
    async with engine.connect() as connection:
        connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
        await connection.execute(
            text(
                "VACUUM (ANALYZE) import_rows, jobs, job_notes, job_line_items, "
                "customers, locations, equipment, technicians, service_categories"
            )
        )


async def execute(args: argparse.Namespace) -> int:
    settings = Settings()
    ensure_local(settings)
    if args.rows < 1 or args.runs < 1 or args.warmup < 0:
        raise ValueError("rows/runs must be positive and warmup must not be negative")
    fixture = render_csv(performance_rows(args.rows))
    if len(fixture.body) > 50 * 1024 * 1024:
        raise RuntimeError("Generated fixture exceeds the Pro 50 MB file limit.")

    owner_engine = build_owner_engine(settings)
    owner_factory = async_sessionmaker(owner_engine, expire_on_commit=False)
    results: list[dict[str, object]] = []
    try:
        version = await postgres_version(owner_factory)
        trial_rows = ([args.warmup] if args.warmup else []) + [args.rows] * args.runs
        for trial_index, rows in enumerate(trial_rows):
            trial_fixture = fixture if rows == args.rows else render_csv(performance_rows(rows))
            token = uuid4().hex
            principal = await ensure_principal(
                owner_factory,
                settings,
                email=f"perf-{token}@example.test",
                password=f"Performance-{token}!",
                organization_name=f"Import performance {token[:8]}",
                organization_slug=f"import-performance-{token}",
                plan_key="pro",
            )
            failed = False
            with tempfile.TemporaryDirectory(prefix="secondtrip-import-perf-") as storage_root:
                run_settings = settings.model_copy(update={"storage_local_path": storage_root})
                storage = LocalStorageProvider(
                    root=Path(storage_root),
                    app_secret=settings.app_secret,
                    base_url=settings.app_url,
                )
                try:
                    run = await run_import(
                        run_settings,
                        principal,
                        storage,
                        trial_fixture.body,
                        MAPPING,
                        original_filename=f"hvac-{rows}.csv",
                        timeout=max(args.max_seconds * 2, 300),
                    )
                    result = asdict(run)
                    result["batch_id"] = str(run.batch_id)
                    result.update(
                        {
                            "rows_requested": rows,
                            "fixture_bytes": len(trial_fixture.body),
                            "fixture_sha256": trial_fixture.sha256,
                            "warmup": rows != args.rows or (trial_index == 0 and bool(args.warmup)),
                        }
                    )
                    results.append(result)
                    print(json.dumps(result, sort_keys=True))
                except BaseException:
                    failed = True
                    if args.keep_on_failure:
                        print(
                            "Preserved failed benchmark tenant: "
                            f"user={principal.user_id} org={principal.organization_id}"
                        )
                    raise
                finally:
                    if not failed or not args.keep_on_failure:
                        await storage.delete_prefix(f"orgs/{principal.organization_id}")
                        await remove_principal(owner_factory, principal)
                        await vacuum_import_tables(owner_engine)

        measured = [item for item in results if not item["warmup"]]
        totals = [cast(float, item["total_seconds"]) for item in measured]
        correct = all(
            item["total_rows"] == args.rows
            and item["created_jobs"] == args.rows
            and item["updated_jobs"] == 0
            and item["error_rows"] == 0
            and item["warning_rows"] == 0
            and item["skipped_rows"] == 0
            and item["import_rows"] == args.rows
            and item["jobs"] == args.rows
            for item in measured
        )
        summary = {
            "environment": {
                "python": platform.python_version(),
                "platform": platform.platform(),
                "postgres": version,
                "git_revision": git_revision(),
                "cpu_count": os.cpu_count(),
                "memory_mib": total_memory_mib(),
                "chunk_size": settings.import_chunk_size,
                "max_rss_kib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            },
            "fixture": {
                "rows": fixture.rows,
                "bytes": len(fixture.body),
                "sha256": fixture.sha256,
            },
            "runs": measured,
            "total_seconds": {
                "min": min(totals),
                "median": statistics.median(totals),
                "max": max(totals),
            },
            "correct": correct,
            "passed": correct and all(value < args.max_seconds for value in totals),
            "threshold_seconds": args.max_seconds,
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        if args.json_out:
            args.json_out.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
        return 0 if summary["passed"] else 1
    finally:
        await owner_engine.dispose()


def main() -> None:
    raise SystemExit(asyncio.run(execute(parse_args())))


if __name__ == "__main__":
    main()
