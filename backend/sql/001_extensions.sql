-- SANKET Platform — PostgreSQL Extensions
-- Run as superuser before any other migration

CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "citext";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "vector";

-- TimescaleDB is optional; comment out if not installed on this instance
-- CREATE EXTENSION IF NOT EXISTS "timescaledb" CASCADE;

-- Verify all extensions loaded
DO $$
DECLARE
    ext TEXT;
    required TEXT[] := ARRAY['pgcrypto','uuid-ossp','citext','pg_trgm','vector'];
BEGIN
    FOREACH ext IN ARRAY required LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_extension WHERE extname = ext) THEN
            RAISE EXCEPTION 'Required extension % failed to load', ext;
        END IF;
    END LOOP;
    RAISE NOTICE 'All required extensions verified.';
END;
$$;
