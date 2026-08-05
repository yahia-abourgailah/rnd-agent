"""Read-only SQL access for the chatbot agent.

The query text here is authored by an LLM, so it is treated as untrusted input.
Three independent layers stand between the model and the database:

1. A least-privilege role (``DATABASE_READONLY_URL``) — the primary defence.
2. A Postgres READ ONLY transaction with a statement timeout — holds even when
   layer 1 is misconfigured and the app's read/write role is in use.
3. `assert_read_only` below — rejects anything that is not a single SELECT/WITH
   before it reaches the server, so the model gets a usable error message
   instead of a driver traceback.
"""

import logging
import re

from langchain_core.tools import tool
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from config.settings import settings

logger = logging.getLogger(__name__)

_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
# Postgres accepts several statements in one simple-query message, so
# "SELECT 1; DROP TABLE launches" would pass a naive prefix check. Statements
# are counted after comments are stripped; a trailing semicolon is tolerated.
_STATEMENT_SEPARATOR = ";"
_ALLOWED_PREFIXES = ("select", "with")
_WRITE_KEYWORDS = re.compile(r"\b(insert|update|delete|merge)\b", re.IGNORECASE)
# Column count across the whole public schema — generous, but bounded so a
# runaway catalogue can't fill the model's context window.
_SCHEMA_ROW_LIMIT = 2000
# The row cap alone does not bound size: `raw` is a JSONB column holding a whole
# source payload, so 100 of them would fill the model's 32k window in a single
# tool result and leave no room to reason about it.
_MAX_TOOL_OUTPUT_CHARS = 6000


def _bounded(text: str) -> str:
    if len(text) <= _MAX_TOOL_OUTPUT_CHARS:
        return text
    return (
        text[:_MAX_TOOL_OUTPUT_CHARS]
        + f"\n... truncated at {_MAX_TOOL_OUTPUT_CHARS} characters. "
        "Select fewer columns, or aggregate in SQL instead of returning rows."
    )


class UnsafeQueryError(ValueError):
    """Raised when LLM-authored SQL is not a single read-only statement."""


def _strip_comments(sql: str) -> str:
    return _BLOCK_COMMENT.sub(" ", _LINE_COMMENT.sub(" ", sql)).strip()


def assert_read_only(sql: str) -> str:
    """Return `sql` (comments stripped) if it is a single SELECT/WITH statement.

    Raises UnsafeQueryError otherwise. Deliberately allow-list based: an
    unrecognised statement is refused rather than passed through, so new DDL
    keywords never silently become reachable.
    """
    stripped = _strip_comments(sql)
    if not stripped:
        raise UnsafeQueryError("Empty query.")

    statements = [part.strip() for part in stripped.split(_STATEMENT_SEPARATOR) if part.strip()]
    if len(statements) > 1:
        raise UnsafeQueryError("Only one statement per query is allowed.")

    statement = statements[0]
    first_word = statement.split(None, 1)[0].lower()
    if first_word not in _ALLOWED_PREFIXES:
        raise UnsafeQueryError(
            f"Only read-only SELECT/WITH queries are allowed, got {first_word.upper()!r}."
        )
    # A CTE can carry a writable body: WITH x AS (DELETE ... RETURNING *) SELECT.
    # Layers 1 and 2 would both reject it; failing here gives a clearer message.
    if first_word == "with" and _WRITE_KEYWORDS.search(statement):
        raise UnsafeQueryError("Data-modifying CTEs are not allowed.")
    return statement


_engine: Engine | None = None


def get_engine() -> Engine:
    """Lazily built, so importing this module never opens a connection.

    Separate from db.engine on purpose: different credentials, and the chatbot
    must not share a connection pool with the write path.
    """
    global _engine
    if _engine is None:
        _engine = create_engine(settings.readonly_database_url, pool_pre_ping=True)
    return _engine


def run_read_only_query(sql: str, max_rows: int | None = None) -> list[tuple]:
    """Execute validated SQL inside a READ ONLY, time-limited transaction.

    `max_rows` defaults to the model-facing cap; internal callers that need a
    complete answer (schema introspection) pass their own.
    """
    statement = assert_read_only(sql)
    limit = settings.chatbot_sql_max_rows if max_rows is None else max_rows
    timeout_ms = int(settings.chatbot_sql_timeout_seconds * 1000)
    with get_engine().connect() as connection:
        # Transaction-scoped: both reset on commit/rollback, so neither leaks
        # into another checkout of the same pooled connection.
        connection.execute(text("SET TRANSACTION READ ONLY"))
        connection.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
        result = connection.execute(text(statement))
        return result.fetchmany(limit)


@tool
def query_database(query: str) -> str:
    """Run a read-only SQL SELECT against the launch-intelligence PostgreSQL
    database and return the matching rows.

    Only a single SELECT (or WITH ... SELECT) statement is accepted; writes and
    schema changes are rejected. Call describe_schema first if you do not know
    the table or column names. At most 100 rows come back, so aggregate in SQL
    and add LIMIT rather than fetching raw rows.
    """
    try:
        rows = run_read_only_query(query)
    except UnsafeQueryError as exc:
        # Expected: the model reached for a disallowed statement. Hand the
        # reason back so it can correct itself on the next turn.
        logger.info("Rejected unsafe query: %s", exc)
        return f"Query rejected: {exc}"
    except Exception as exc:
        # Malformed SQL is the model's problem to fix, but this same path
        # catches problems that are ours (schema drift, dead connection), so it
        # is logged with a traceback rather than swallowed.
        logger.exception("Query failed")
        return f"Database error: {type(exc).__name__}: {exc}"

    if not rows:
        return "No rows returned."
    return _bounded("\n".join(str(tuple(row)) for row in rows))


@tool
def describe_schema() -> str:
    """List the tables and columns available in the launch-intelligence
    database. Call this before writing a query so column names are exact.
    """
    catalogue_query = """
        SELECT table_name, column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public'
        ORDER BY table_name, ordinal_position
    """
    try:
        # Not subject to the model-facing row cap: a truncated catalogue would
        # silently hide tables and send the model guessing at column names.
        rows = run_read_only_query(catalogue_query, max_rows=_SCHEMA_ROW_LIMIT)
    except Exception as exc:
        logger.exception("Schema introspection failed")
        return f"Database error: {type(exc).__name__}: {exc}"

    tables: dict[str, list[str]] = {}
    for table_name, column_name, data_type in rows:
        tables.setdefault(table_name, []).append(f"{column_name} {data_type}")
    return _bounded(
        "\n".join(f"{name}({', '.join(columns)})" for name, columns in tables.items())
    )


TOOLS = [describe_schema, query_database]
