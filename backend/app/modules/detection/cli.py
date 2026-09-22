"""Local detection proof: enqueue the production path and print its evidence."""

from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.composition import build_storage_provider
from app.core.settings import Settings
from app.core.tenancy import TenantContext
from app.db.engine import build_engine, build_session_factory
from app.db.session import tenant_session
from app.modules.detection.models import CandidateSignal, DetectionRun, ReworkCandidate
from app.modules.detection.schemas import DetectionRunStatus, DetectionTrigger
from app.modules.detection.service import enqueue_detection_run
from app.modules.tasks.handlers import build_job_registry
from app.modules.tasks.service import PostgresJobQueue
from app.modules.tasks.worker import BackgroundWorker


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run deterministic detection for one tenant.")
    parser.add_argument("--org", type=UUID, required=True, help="Organization UUID")
    parser.add_argument("--from", dest="from_date", type=date.fromisoformat)
    parser.add_argument("--to", dest="to_date", type=date.fromisoformat)
    parser.add_argument("--timeout", type=float, default=300)
    return parser.parse_args()


async def execute() -> int:
    arguments = _arguments()
    settings = Settings()
    today = datetime.now(UTC).date()
    from_date = arguments.from_date or today - timedelta(days=90)
    to_date = arguments.to_date or today
    if from_date > to_date:
        raise ValueError("--from must be on or before --to")

    engine = build_engine(settings)
    factory = build_session_factory(engine)
    tenant = TenantContext(
        organization_id=arguments.org,
        request_id=f"detect-cli:{uuid4()}",
    )
    configured = settings.model_copy(
        update={"worker_id": f"detect-cli-{uuid4()}", "worker_concurrency": 1}
    )
    worker = BackgroundWorker(
        session_factory=factory,
        registry=build_job_registry(build_storage_provider(settings), factory, configured),
        settings=configured,
    )
    queue = PostgresJobQueue(default_max_attempts=settings.job_max_attempts)
    try:
        async with tenant_session(factory, tenant) as session:
            run = await enqueue_detection_run(
                session,
                queue,
                settings,
                tenant,
                trigger=DetectionTrigger.MANUAL,
                from_date=from_date,
                to_date=to_date,
            )
            run_id = run.id

        worker.start()
        deadline = asyncio.get_running_loop().time() + arguments.timeout
        while True:
            async with tenant_session(factory, tenant) as session:
                status = await session.scalar(
                    select(DetectionRun.status).where(DetectionRun.id == run_id)
                )
            if status is DetectionRunStatus.COMPLETED:
                break
            if status in {DetectionRunStatus.FAILED, DetectionRunStatus.CANCELLED}:
                raise RuntimeError(f"Detection run ended with status {status.value}.")
            if asyncio.get_running_loop().time() >= deadline:
                raise TimeoutError("Detection run did not finish before --timeout.")
            await asyncio.sleep(0.1)

        await _print_results(factory, tenant, run_id)
        return 0
    finally:
        await worker.stop(grace_seconds=5)
        await engine.dispose()


async def _print_results(
    factory: async_sessionmaker[AsyncSession],
    tenant: TenantContext,
    run_id: UUID,
) -> None:
    # Kept separate from execution so the CLI remains a read-only renderer over persisted truth.
    async with tenant_session(factory, tenant) as session:
        run = await session.get(DetectionRun, run_id)
        assert run is not None
        candidates = list(
            (
                await session.execute(
                    select(ReworkCandidate)
                    .where(
                        ReworkCandidate.current_detection_run_id == run_id,
                        ReworkCandidate.is_suppressed.is_(False),
                    )
                    .order_by(
                        ReworkCandidate.current_normalized_score.desc(),
                        ReworkCandidate.id,
                    )
                    .limit(50)
                )
            )
            .scalars()
            .all()
        )
        evidence = list(
            (
                await session.execute(
                    select(CandidateSignal)
                    .where(
                        CandidateSignal.detection_run_id == run_id,
                        CandidateSignal.candidate_id.in_([item.id for item in candidates]),
                    )
                    .order_by(CandidateSignal.candidate_id, CandidateSignal.signal_key)
                )
            )
            .scalars()
            .all()
        )

    print(
        f"run={run.id} status={run.status.value} pairs={run.pairs_evaluated} "
        f"created={run.candidates_created} updated={run.candidates_updated} "
        f"suppressed={run.candidates_suppressed}"
    )
    by_candidate: dict[UUID, list[CandidateSignal]] = {}
    for signal in evidence:
        by_candidate.setdefault(signal.candidate_id, []).append(signal)
    for index, candidate in enumerate(candidates, start=1):
        score = candidate.current_normalized_score or Decimal(0)
        band = candidate.score_band.value if candidate.score_band else "unscored"
        print(
            f"\n{index:02d}. {candidate.prior_job_id} -> {candidate.followup_job_id} "
            f"score={score} band={band} days={candidate.days_between}"
        )
        for signal in by_candidate.get(candidate.id, []):
            print(
                f"    {signal.signal_key}: {signal.outcome.value} "
                f"contribution={signal.contribution} — {signal.explanation}"
            )


def main() -> None:
    raise SystemExit(asyncio.run(execute()))


if __name__ == "__main__":
    main()
