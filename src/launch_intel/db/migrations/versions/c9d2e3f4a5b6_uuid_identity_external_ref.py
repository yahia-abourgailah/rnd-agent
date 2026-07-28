"""relational identity: UUID primary keys + external_ref

Switches developers/areas/projects/units/availability from a source-derived
BigInteger key to a UUID WE generate, with the origin's id kept only as
`external_ref` ("nawy:1198") for re-sync matching. The relational data is fully
reproducible from Nawy, so this drops and recreates those tables rather than
doing an in-place type migration. Run the backfill again afterwards.

Revision ID: c9d2e3f4a5b6
Revises: b7f1a2c3d4e5
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c9d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = 'b7f1a2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_UUID = postgresql.UUID(as_uuid=True)
_UUID_DEFAULT = sa.text('gen_random_uuid()')  # native in PostgreSQL 13+


def _create_relational() -> None:
    op.create_table(
        'developers',
        sa.Column('id', _UUID, server_default=_UUID_DEFAULT, nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('external_ref', sa.String(length=128), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=255), nullable=True),
        sa.Column('logo_url', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('projects_count', sa.Integer(), nullable=True),
        sa.Column('raw', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('first_seen_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('external_ref', name='uq_developers_ref'),
    )
    op.create_table(
        'areas',
        sa.Column('id', _UUID, server_default=_UUID_DEFAULT, nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('external_ref', sa.String(length=128), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=255), nullable=True),
        sa.Column('city', sa.String(length=255), nullable=True),
        sa.Column('raw', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('external_ref', name='uq_areas_ref'),
    )
    op.create_table(
        'projects',
        sa.Column('id', _UUID, server_default=_UUID_DEFAULT, nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('external_ref', sa.String(length=128), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=255), nullable=True),
        sa.Column('developer_id', _UUID, nullable=True),
        sa.Column('area_id', _UUID, nullable=True),
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
        sa.UniqueConstraint('external_ref', name='uq_projects_ref'),
    )
    op.create_index('ix_projects_developer_id', 'projects', ['developer_id'], unique=False)
    op.create_index('ix_projects_area_id', 'projects', ['area_id'], unique=False)
    op.create_index('ix_projects_is_launch', 'projects', ['is_launch'], unique=False)
    op.create_table(
        'units',
        sa.Column('id', _UUID, server_default=_UUID_DEFAULT, nullable=False),
        sa.Column('source', sa.String(length=50), nullable=False),
        sa.Column('external_ref', sa.String(length=128), nullable=False),
        sa.Column('project_id', _UUID, nullable=True),
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
        sa.UniqueConstraint('external_ref', name='uq_units_ref'),
    )
    op.create_index('ix_units_project_id', 'units', ['project_id'], unique=False)
    op.create_table(
        'availability',
        sa.Column('id', _UUID, server_default=_UUID_DEFAULT, nullable=False),
        sa.Column('project_id', _UUID, nullable=False),
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


def _drop_relational() -> None:
    op.drop_table('availability')
    op.drop_table('units')
    op.drop_table('projects')
    op.drop_table('areas')
    op.drop_table('developers')


def upgrade() -> None:
    # launches.project_id points at projects; detach it before recreating.
    op.drop_constraint('fk_launches_project_id', 'launches', type_='foreignkey')
    op.drop_column('launches', 'project_id')

    _drop_relational()
    _create_relational()

    # Re-attach launches.project_id as a UUID FK to the new projects.id.
    op.add_column('launches', sa.Column('project_id', _UUID, nullable=True))
    op.create_foreign_key('fk_launches_project_id', 'launches', 'projects', ['project_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_launches_project_id', 'launches', type_='foreignkey')
    op.drop_column('launches', 'project_id')
    _drop_relational()

    # Recreate the previous BigInteger / (source, source_id) schema.
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
    op.add_column('launches', sa.Column('project_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key('fk_launches_project_id', 'launches', 'projects', ['project_id'], ['id'])
