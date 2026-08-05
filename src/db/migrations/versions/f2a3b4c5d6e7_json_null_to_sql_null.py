"""Normalise JSON 'null' payloads to SQL NULL

Python None was written into JSONB columns as JSON `null` instead of SQL NULL,
so `raw IS NULL` never matched and the COALESCE in the entity upsert could not
tell "no payload" from "a payload that happens to be null" — letting a partial
re-sync blank a stored payload. db/tables.py now sets none_as_null; this cleans
the rows written before that.

Revision ID: f2a3b4c5d6e7
Revises: e1f2a3b4c5d6
"""

from alembic import op

revision = "f2a3b4c5d6e7"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None

_JSON_COLUMNS = [
    ("developers", "raw"),
    ("areas", "raw"),
    ("projects", "raw"),
    ("units", "raw"),
    ("launches", "unit_sizes"),
]


def upgrade() -> None:
    for table, column in _JSON_COLUMNS:
        op.execute(
            f"UPDATE {table} SET {column} = NULL "  # noqa: S608 - fixed identifiers above
            f"WHERE {column} IS NOT NULL AND jsonb_typeof({column}) = 'null'"
        )


def downgrade() -> None:
    # Restoring JSON 'null' would reintroduce the defect; SQL NULL is a strict
    # improvement and the two are equivalent to every reader.
    pass
