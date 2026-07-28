"""dedup: canonical_id self-links on developers and projects

A duplicate row (same real entity from another source) points at the canonical
row via canonical_id; NULL means canonical/standalone. Set by dedup/resolver.py.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'e1f2a3b4c5d6'
down_revision: Union[str, Sequence[str], None] = 'd0e1f2a3b4c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column('developers', sa.Column('canonical_id', _UUID, nullable=True))
    op.create_foreign_key('fk_developers_canonical', 'developers', 'developers', ['canonical_id'], ['id'])
    op.create_index('ix_developers_canonical_id', 'developers', ['canonical_id'], unique=False)

    op.add_column('projects', sa.Column('canonical_id', _UUID, nullable=True))
    op.create_foreign_key('fk_projects_canonical', 'projects', 'projects', ['canonical_id'], ['id'])
    op.create_index('ix_projects_canonical_id', 'projects', ['canonical_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_projects_canonical_id', table_name='projects')
    op.drop_constraint('fk_projects_canonical', 'projects', type_='foreignkey')
    op.drop_column('projects', 'canonical_id')

    op.drop_index('ix_developers_canonical_id', table_name='developers')
    op.drop_constraint('fk_developers_canonical', 'developers', type_='foreignkey')
    op.drop_column('developers', 'canonical_id')
