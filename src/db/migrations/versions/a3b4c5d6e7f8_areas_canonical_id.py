"""Add canonical_id to areas

Developers and projects were deduplicated across sources but areas were not, so
the same zone existed once per source ("New Cairo" from Nawy, "New Cairo City"
from Property Finder) and every zone-level aggregate was split between them.

Revision ID: a3b4c5d6e7f8
Revises: f2a3b4c5d6e7
"""

import sqlalchemy as sa
from alembic import op

revision = "a3b4c5d6e7f8"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("areas", sa.Column("canonical_id", sa.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_areas_canonical_id", "areas", "areas", ["canonical_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_areas_canonical_id", "areas", ["canonical_id"])


def downgrade() -> None:
    op.drop_index("ix_areas_canonical_id", table_name="areas")
    op.drop_constraint("fk_areas_canonical_id", "areas", type_="foreignkey")
    op.drop_column("areas", "canonical_id")
