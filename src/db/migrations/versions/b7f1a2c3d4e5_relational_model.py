"""relational model: developers, areas, projects, units, availability

Adds the connected entity tables (the mentor's ask) alongside the existing flat
`launches` table, and links launches to projects via a nullable project_id.
Purely additive: nothing in the existing pipeline changes shape.

Revision ID: b7f1a2c3d4e5
Revises: e2a4ce81c85e
Create Date: 2026-07-26 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'b7f1a2c3d4e5'
down_revision: Union[str, Sequence[str], None] = 'e2a4ce81c85e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'developers',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('source_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=255), nullable=True),
        sa.Column('logo_url', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('projects_count', sa.Integer(), nullable=True),
        sa.Column('raw', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source', 'source_id', name='uq_developers_source'),
    )
    op.create_table(
        'areas',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('source_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=255), nullable=True),
        sa.Column('city', sa.String(length=255), nullable=True),
        sa.Column('raw', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source', 'source_id', name='uq_areas_source'),
    )
    op.create_table(
        'projects',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('source_id', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=255), nullable=True),
        sa.Column('developer_id', sa.BigInteger(), nullable=True),
        sa.Column('area_id', sa.BigInteger(), nullable=True),
        sa.Column('min_price', sa.Float(), nullable=True),
        sa.Column('currency', sa.String(length=8), nullable=True),
        sa.Column('property_types', postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column('is_launch', sa.Boolean(), nullable=False),
        sa.Column('delivery_date', sa.String(length=64), nullable=True),
        sa.Column('image_url', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('raw', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['developer_id'], ['developers.id'], ),
        sa.ForeignKeyConstraint(['area_id'], ['areas.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source', 'source_id', name='uq_projects_source'),
    )
    op.create_index('ix_projects_developer_id', 'projects', ['developer_id'], unique=False)
    op.create_index('ix_projects_area_id', 'projects', ['area_id'], unique=False)
    op.create_index('ix_projects_is_launch', 'projects', ['is_launch'], unique=False)
    op.create_table(
        'units',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('source_id', sa.String(length=64), nullable=False),
        sa.Column('project_id', sa.BigInteger(), nullable=True),
        sa.Column('property_type', sa.String(length=64), nullable=True),
        sa.Column('unit_area_sqm', sa.Float(), nullable=True),
        sa.Column('bedrooms', sa.Integer(), nullable=True),
        sa.Column('bathrooms', sa.Integer(), nullable=True),
        sa.Column('price', sa.Float(), nullable=True),
        sa.Column('currency', sa.String(length=8), nullable=True),
        sa.Column('ready_by', sa.String(length=32), nullable=True),
        sa.Column('finishing', sa.String(length=64), nullable=True),
        sa.Column('raw', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('source', 'source_id', name='uq_units_source'),
    )
    op.create_index('ix_units_project_id', 'units', ['project_id'], unique=False)
    op.create_table(
        'availability',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('project_id', sa.BigInteger(), nullable=False),
        sa.Column('snapshot_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('total_units', sa.Integer(), nullable=True),
        sa.Column('available_units', sa.Integer(), nullable=True),
        sa.Column('min_price', sa.Float(), nullable=True),
        sa.Column('max_price', sa.Float(), nullable=True),
        sa.Column('price_per_sqm_min', sa.Float(), nullable=True),
        sa.Column('price_per_sqm_max', sa.Float(), nullable=True),
        sa.Column('unit_types', postgresql.ARRAY(sa.String()), nullable=False),
        sa.Column('delivery_range', sa.String(length=64), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_availability_project_snapshot', 'availability', ['project_id', 'snapshot_at'], unique=False
    )
    # Link the existing flat launches table to its canonical project. Nullable,
    # so existing rows and the current pipeline are unaffected.
    op.add_column('launches', sa.Column('project_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key(
        'fk_launches_project_id', 'launches', 'projects', ['project_id'], ['id']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_launches_project_id', 'launches', type_='foreignkey')
    op.drop_column('launches', 'project_id')
    op.drop_index('ix_availability_project_snapshot', table_name='availability')
    op.drop_table('availability')
    op.drop_index('ix_units_project_id', table_name='units')
    op.drop_table('units')
    op.drop_index('ix_projects_is_launch', table_name='projects')
    op.drop_index('ix_projects_area_id', table_name='projects')
    op.drop_index('ix_projects_developer_id', table_name='projects')
    op.drop_table('projects')
    op.drop_table('areas')
    op.drop_table('developers')
