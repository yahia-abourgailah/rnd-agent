"""sources registry + source_id foreign keys

Normalises provenance: adds a `sources` table (nawy = 1, property_finder = 2,
...) and replaces the repeated `source` string on each relational entity with a
`source_id` FK to it. Done in place — existing rows (all Nawy) are backfilled to
source_id = 1, so no reload is needed.

Revision ID: d0e1f2a3b4c5
Revises: c9d2e3f4a5b6
Create Date: 2026-07-27 00:00:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd0e1f2a3b4c5'
down_revision: str | Sequence[str] | None = 'c9d2e3f4a5b6'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ENTITY_TABLES = ('developers', 'areas', 'projects', 'units')


def upgrade() -> None:
    # 1. The sources registry.
    op.create_table(
        'sources',
        sa.Column('id', sa.Integer(), autoincrement=False, nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('display_name', sa.String(length=100), nullable=False),
        sa.Column('base_url', sa.Text(), nullable=True),
        sa.Column('source_type', sa.String(length=32), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default=sa.text('false'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name', name='uq_sources_name'),
    )
    op.execute(
        """
        INSERT INTO sources (id, name, display_name, base_url, source_type, is_active, created_at) VALUES
          (1, 'nawy',            'Nawy',            'https://www.nawy.com',                  'aggregator',     true,  now()),
          (2, 'property_finder', 'Property Finder', 'https://www.propertyfinder.eg',         'aggregator',     false, now()),
          (3, 'sodic',           'SODIC',           'https://www.sodic.com',                 'developer_site', false, now()),
          (4, 'palm_hills',      'Palm Hills',      'https://www.palmhillsdevelopments.com', 'developer_site', false, now())
        """
    )

    # 2. Entity tables that already carry a `source` string: add the FK, copy
    #    the value across by matching the source name, enforce, then drop the string.
    for tbl in _ENTITY_TABLES:
        op.add_column(tbl, sa.Column('source_id', sa.Integer(), nullable=True))
        op.execute(f"UPDATE {tbl} t SET source_id = s.id FROM sources s WHERE s.name = t.source")
        op.alter_column(tbl, 'source_id', nullable=False)
        op.create_foreign_key(f'fk_{tbl}_source_id', tbl, 'sources', ['source_id'], ['id'])
        op.drop_column(tbl, 'source')

    # 3. Availability has no `source` column — derive it from its project.
    op.add_column('availability', sa.Column('source_id', sa.Integer(), nullable=True))
    op.execute(
        "UPDATE availability a SET source_id = p.source_id FROM projects p WHERE a.project_id = p.id"
    )
    op.alter_column('availability', 'source_id', nullable=False)
    op.create_foreign_key('fk_availability_source_id', 'availability', 'sources', ['source_id'], ['id'])

    # 4. Filter indexes on the large tables.
    op.create_index('ix_projects_source_id', 'projects', ['source_id'], unique=False)
    op.create_index('ix_units_source_id', 'units', ['source_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_units_source_id', table_name='units')
    op.drop_index('ix_projects_source_id', table_name='projects')

    op.drop_constraint('fk_availability_source_id', 'availability', type_='foreignkey')
    op.drop_column('availability', 'source_id')

    for tbl in _ENTITY_TABLES:
        op.add_column(tbl, sa.Column('source', sa.String(length=50), nullable=True))
        op.execute(f"UPDATE {tbl} t SET source = s.name FROM sources s WHERE s.id = t.source_id")
        op.alter_column(tbl, 'source', nullable=False)
        op.drop_constraint(f'fk_{tbl}_source_id', tbl, type_='foreignkey')
        op.drop_column(tbl, 'source_id')

    op.drop_table('sources')
