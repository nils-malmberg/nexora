-- Runs once, on first initialization of the postgres_data volume (the
-- official postgres image's normal behaviour for /docker-entrypoint-initdb.d
-- scripts - it will NOT re-run against an existing volume). Creates a
-- second, fully independent database for the Portfolio module, alongside
-- the default `nexora` database used by the News & Events module - separate
-- schemas and migration histories, same Postgres server.
SELECT 'CREATE DATABASE nexora_portfolio OWNER ' || current_user
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'nexora_portfolio')
\gexec
