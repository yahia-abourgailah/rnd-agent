"""Add sale_type to units

The catalogue tracks primary/off-plan stock. Resale units were being ingested
because nothing read the source's sale-type flag; they are now filtered at
collection, and this column records the decision so a resale row that slips
through is visible rather than indistinguishable.

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
"""

import sqlalchemy as sa
from alembic import op

revision = "b4c5d6e7f8a9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("units", sa.Column("sale_type", sa.String(16), nullable=True))
    op.create_index("ix_units_sale_type", "units", ["sale_type"])


def downgrade() -> None:
    op.drop_index("ix_units_sale_type", table_name="units")
    op.drop_column("units", "sale_type")
