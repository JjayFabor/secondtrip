-- Role bootstrap — see docs/architecture/02-multi-tenancy.md §2 and
-- CLAUDE.md rule 4.
--
-- Run ONCE per database, connected AS the role that will run Alembic
-- migrations (DATABASE_URL_MIGRATIONS) — required because ALTER DEFAULT
-- PRIVILEGES below applies to future objects created BY THE ROLE THAT
-- EXECUTES THIS SCRIPT, with no role specified. Used both against Neon
-- (manually, via psql against DATABASE_URL_MIGRATIONS) and locally
-- (mounted into the Postgres container's /docker-entrypoint-initdb.d/,
-- which runs as POSTGRES_USER — set to the local owner role below — so
-- `docker compose up` applies it automatically on first boot) — local dev
-- must behave like production or RLS bugs are discovered for the first
-- time in prod.
--
-- secondtrip_app is the ONLY role the application ever connects as. It:
--   * does NOT own any table (the migration role does), so it cannot
--     bypass a table's own RLS policies the way an owner can by default
--   * does NOT have BYPASSRLS (the default for a new role; stated
--     explicitly here so the intent is not just an accident of defaults)
--   * gets SELECT/INSERT/UPDATE/DELETE via ALTER DEFAULT PRIVILEGES, so
--     every table a future migration creates is automatically covered
--     without that migration having to remember a GRANT statement

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'secondtrip_app') THEN
        -- Local-dev-only password. Production/Neon: create this role via
        -- the provider's console or `ALTER ROLE ... PASSWORD` with a real
        -- secret from the secret manager BEFORE pointing DATABASE_URL at
        -- it — never reuse this value outside local development.
        CREATE ROLE secondtrip_app WITH LOGIN PASSWORD 'secondtrip_app_dev_only' NOBYPASSRLS NOSUPERUSER NOCREATEDB NOCREATEROLE;
    END IF;
END
$$;

GRANT USAGE ON SCHEMA public TO secondtrip_app;

-- Covers tables that already exist at the time this script runs.
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO secondtrip_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO secondtrip_app;

-- Covers every table/sequence a FUTURE migration creates, as long as the
-- migration runs as the same role that executes this block (the owner /
-- DATABASE_URL_MIGRATIONS role). Without this, every new table needs a
-- manual GRANT or the app silently loses access to it.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO secondtrip_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO secondtrip_app;

-- audit_events is append-only at the database level, not by convention —
-- see docs/architecture/13-audit.md §2. Applied here as a template;
-- Phase 3's audit_events migration re-runs the revoke once the table
-- exists, since this DEFAULT PRIVILEGES grant above would otherwise hand
-- it UPDATE/DELETE like every other table.
-- REVOKE UPDATE, DELETE ON audit_events FROM secondtrip_app;
