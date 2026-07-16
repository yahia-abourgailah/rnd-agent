-- Runs automatically on FIRST container startup (docker-entrypoint-initdb.d).
-- The pgvector/pgvector image ships the extension binaries; this actually
-- enables it in the launch_intel database so vector columns work.
CREATE EXTENSION IF NOT EXISTS vector;
