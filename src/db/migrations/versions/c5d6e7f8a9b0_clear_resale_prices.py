"""Recompute project prices that came from a resale plan

map_compound used to fall back developerPlan -> resalePlan for every field, so a
compound with no developer price stored a secondary-market price as the
project's asking price. The mapper now reads the developer plan only, but the
entity upsert COALESCEs against the stored value and therefore never blanks the
rows already written — 101 of them on first observation.

The original payload is kept in projects.raw, so the correct value is derived
from it rather than guessed.

Revision ID: c5d6e7f8a9b0
Revises: b4c5d6e7f8a9
"""

from alembic import op

revision = "c5d6e7f8a9b0"
down_revision = "b4c5d6e7f8a9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Scoped by source, not by the presence of a developerPlan key: Nawy omits
    # that key entirely on some compounds and sends it with a null price on
    # others, and it is precisely the omitted ones that hold a resale price.
    # `->>` yields NULL for both shapes, which is the value wanted here.
    op.execute(
        """
        UPDATE projects p
        SET min_price = NULLIF(p.raw->'developerPlan'->>'minPrice', '')::numeric,
            currency  = NULLIF(p.raw->'developerPlan'->>'currency', '')
        FROM sources s
        WHERE s.id = p.source_id
          AND s.name = 'nawy'
          AND p.raw IS NOT NULL
          AND p.min_price IS DISTINCT FROM
              NULLIF(p.raw->'developerPlan'->>'minPrice', '')::numeric
        """
    )


def downgrade() -> None:
    # Restoring resale prices into a primary-price column would reintroduce the
    # defect; there is nothing worth going back to.
    pass
