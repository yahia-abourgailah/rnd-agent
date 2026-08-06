-- Runs automatically on FIRST container startup (docker-entrypoint-initdb.d).
--
-- The chatbot agent executes SQL written by an LLM. Its credentials must not be
-- able to write, so it gets its own role with SELECT and nothing else. The
-- READ ONLY transaction and the query parser in chatbot_agent/tools/postgres.py
-- are backstops; this role is the actual boundary.
--
-- The password is a local-development default and is overridden per environment
-- via DATABASE_READONLY_URL. Production must not use it.

CREATE ROLE launch_intel_ro LOGIN PASSWORD 'ro_local_dev';

GRANT CONNECT ON DATABASE launch_intel TO launch_intel_ro;
GRANT USAGE ON SCHEMA public TO launch_intel_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO launch_intel_ro;

-- Tables created later — by migrations, or by LangGraph's checkpointer — are
-- covered without anyone remembering to re-grant.
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO launch_intel_ro;

-- Explicitly withhold everything else, including on future objects: a role that
-- can create tables in public can also shadow ours.
REVOKE CREATE ON SCHEMA public FROM launch_intel_ro;
REVOKE ALL ON DATABASE launch_intel FROM PUBLIC;
