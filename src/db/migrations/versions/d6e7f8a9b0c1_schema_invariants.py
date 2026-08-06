"""Enforce the catalogue's invariants in the database

Every rule the mappers uphold was enforced only on the Python write path, so a
manual UPDATE, a psql session, a script that bypasses the mapper or a restored
backup could violate it silently — and the first symptom is a wrong number in a
report. The chatbot writes its own SQL against these tables, which makes silent
violations especially expensive.

Also makes canonical_id behave the same way everywhere. It meant one thing and
behaved three ways: SET NULL on areas, NO ACTION on developers and projects, so
deleting a canonical area un-deduplicated its duplicates while deleting a
canonical developer raised a foreign key error.

And adds the availability uniqueness a run needs to be retry-safe, ordered
(source_id, project_id, snapshot_at) so the same index also serves per-source
history queries.

Every constraint here was verified against the live catalogue before being
written: 2,135 projects, 8,496 units, 878 snapshots, zero violations.

Revision ID: d6e7f8a9b0c1
Revises: c5d6e7f8a9b0
"""

from alembic import op

revision = "d6e7f8a9b0c1"
down_revision = "c5d6e7f8a9b0"
branch_labels = None
depends_on = None

_CHECKS = [
    (
        "projects",
        "ck_projects_delivery_date_is_year",
        "delivery_date IS NULL OR delivery_date ~ '^[0-9]{4}$'",
    ),
    ("projects", "ck_projects_min_price_non_negative", "min_price IS NULL OR min_price >= 0"),
    (
        "projects",
        "ck_projects_property_types_canonical",
        "property_types IS NULL OR ("
        "array_to_string(property_types, ',') = lower(array_to_string(property_types, ',')) "
        "AND array_to_string(property_types, ',') NOT LIKE '% %')",
    ),
    ("projects", "ck_projects_canonical_not_self", "canonical_id IS NULL OR canonical_id <> id"),
    (
        "developers",
        "ck_developers_canonical_not_self",
        "canonical_id IS NULL OR canonical_id <> id",
    ),
    ("areas", "ck_areas_canonical_not_self", "canonical_id IS NULL OR canonical_id <> id"),
    (
        "units",
        "ck_units_sale_type_known",
        "sale_type IS NULL OR sale_type IN ('primary', 'resale')",
    ),
    ("units", "ck_units_price_non_negative", "price IS NULL OR price >= 0"),
    ("units", "ck_units_area_non_negative", "unit_area_sqm IS NULL OR unit_area_sqm >= 0"),
]

_CANONICAL_FKS = [
    ("developers", "fk_developers_canonical"),
    ("projects", "fk_projects_canonical"),
]


def upgrade() -> None:
    for table, name, condition in _CHECKS:
        op.create_check_constraint(name, table, condition)

    # A duplicate whose canonical row disappears should become canonical again,
    # not block the delete.
    for table, name in _CANONICAL_FKS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(
            name, table, table, ["canonical_id"], ["id"], ondelete="SET NULL"
        )

    op.drop_index("ix_availability_project_snapshot", table_name="availability")
    op.create_unique_constraint(
        "uq_availability_source_project_run",
        "availability",
        ["source_id", "project_id", "snapshot_at"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_availability_source_project_run", "availability", type_="unique")
    op.create_index(
        "ix_availability_project_snapshot", "availability", ["project_id", "snapshot_at"]
    )

    for table, name in _CANONICAL_FKS:
        op.drop_constraint(name, table, type_="foreignkey")
        op.create_foreign_key(name, table, table, ["canonical_id"], ["id"])

    for table, name, _ in _CHECKS:
        op.drop_constraint(name, table, type_="check")
