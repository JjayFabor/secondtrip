# Migration and rollback runbook

SecondTrip uses Alembic migrations, a separate database-owner connection, and Neon restore
points. Application rollback and data rollback are deliberately separate decisions.

## Before every production deploy

1. Require green backend, frontend, and contract checks for the release SHA.
2. Record the current application SHA and Alembic revision:

   ```bash
   git rev-parse HEAD
   cd backend
   uv run alembic current
   uv run alembic heads
   uv run alembic check
   ```

3. Create and name a Neon restore point, snapshot, or branch immediately before migration.
4. Confirm the previous application artifact or commit is still deployable.
5. Check for active imports/background jobs. For a risky migration, stop new writes and set
   Render maintenance mode before continuing.

## Apply

Render runs this as its pre-deploy command using `DATABASE_URL_MIGRATIONS`:

```bash
cd backend
uv run alembic upgrade head
```

The running API uses `DATABASE_URL`, the non-owner pooled connection. It must never run schema
migrations.

After deployment:

```bash
./scripts/smoke-deployment.sh \
  https://secondtrip.jjayfabor.com \
  https://api.secondtrip.jjayfabor.com
```

Then complete the authenticated import/detection/review smoke flow from
[`production-launch.md`](production-launch.md).

## Roll back application code only

Use this when the database migration is backward-compatible and data is sound:

1. Redeploy the previous release SHA in Render and Vercel.
2. Leave the schema at its newer revision.
3. Run `/health`, `/ready`, and the smoke script.
4. Confirm the old application understands any queued job payloads created by the newer release.

This is the normal rollback. Additive schema changes should make it possible.

## Restore data and schema

Use this when a migration or release has corrupted data or is not backward-compatible:

1. Enable maintenance mode and stop the API/worker so no new writes occur.
2. Record the incident time and current database revision.
3. Restore the pre-deploy Neon point into an isolated branch first and verify row counts,
   tenant isolation, and the expected Alembic revision.
4. Promote or switch to the verified restored branch using the current Neon procedure.
5. Redeploy the previous application release.
6. Run readiness, security, and authenticated end-to-end smoke checks before reopening traffic.
7. Preserve the failed branch for investigation; do not copy individual tenant rows manually.

Do not run `alembic downgrade` in production as an improvised recovery step. Some repository
migrations are intentionally forward-only, and a downgrade cannot recover data removed or
rewritten by application code. Use downgrade only when that exact revision path has been tested
against a disposable copy and the incident owner explicitly chooses it.

## Failed pre-deploy migration

If `alembic upgrade head` fails before Render sends traffic to the new instance:

1. Keep the old application serving only if the partially applied schema remains compatible.
2. Inspect the Alembic revision and PostgreSQL transaction outcome. PostgreSQL transactional DDL
   usually rolls back the failed revision, but verify rather than assume.
3. If the schema or data is uncertain, enter maintenance mode and use the restore procedure.
4. Fix forward with a new migration; never edit an already-applied migration file.
