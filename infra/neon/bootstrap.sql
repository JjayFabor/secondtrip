-- Role bootstrap — see docs/architecture/02-multi-tenancy.md §2 and
-- CLAUDE.md rule 4.
--
-- Run ONCE per database, connected AS the role that will run Alembic
-- migrations (DATABASE_URL_MIGRATIONS) — required because ALTER DEFAULT
-- PRIVILEGES below applies to future objects created BY THE ROLE THAT
-- EXECUTES THIS SCRIPT, with no role specified. Used both against Neon
-- (manually, via psql against DATABASE_URL_MIGRATIONS) and locally after
-- local-role.sql creates the development-only role. This script never creates
-- credentials: production must create secondtrip_app with a unique password
-- first, and local development keeps its known password in local-role.sql.
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
        RAISE EXCEPTION 'secondtrip_app must exist before bootstrap; create it with a unique password and no elevated attributes';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_roles
        WHERE rolname = 'secondtrip_app'
          AND (rolsuper OR rolbypassrls OR rolcreatedb OR rolcreaterole OR rolreplication)
    ) THEN
        RAISE EXCEPTION 'secondtrip_app has elevated attributes and is unsafe for RLS';
    END IF;

    IF EXISTS (
        SELECT 1
        FROM pg_catalog.pg_auth_members memberships
        JOIN pg_catalog.pg_roles granted_role ON granted_role.oid = memberships.roleid
        JOIN pg_catalog.pg_roles member_role ON member_role.oid = memberships.member
        WHERE member_role.rolname = 'secondtrip_app'
          AND granted_role.rolname = 'neon_superuser'
    ) THEN
        RAISE EXCEPTION 'secondtrip_app must not inherit neon_superuser';
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
