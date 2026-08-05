"""Postgres-backed conversation memory for the chatbot graph.

Use `conversation_checkpointer()` as a context manager for the lifetime of the
process (FastAPI lifespan, or the CLI's main loop); it yields a PostgresSaver
with its tables created.

This writes, so it uses `database_url` rather than the read-only URL the SQL
tool runs on.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from sqlalchemy.engine import make_url

from config.settings import settings


def psycopg_dsn(sqlalchemy_url: str) -> str:
    """Convert a SQLAlchemy URL to the plain libpq DSN psycopg expects."""
    return make_url(sqlalchemy_url).set(drivername="postgresql").render_as_string(
        hide_password=False
    )


@contextmanager
def conversation_checkpointer() -> Iterator[PostgresSaver]:
    with PostgresSaver.from_conn_string(psycopg_dsn(settings.database_url)) as saver:
        saver.setup()
        yield saver
