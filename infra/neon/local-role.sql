-- Local development only. Production roles must be created with a unique
-- password before infra/neon/bootstrap.sql runs.
CREATE ROLE secondtrip_app WITH
    LOGIN
    PASSWORD 'secondtrip_app_dev_only'
    NOBYPASSRLS
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION;
