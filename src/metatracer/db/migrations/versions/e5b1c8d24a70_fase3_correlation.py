"""fase 3: shared-value correlation

Revision ID: e5b1c8d24a70
Revises: c3d8a1e57f04
Create Date: 2026-10-29 22:00:00.000000

Adds ``value_entity`` and ``asset_value``. A shared hash means a shared
observed value, not a shared identity. SQLite creates both tables through
``init_db``. ``internal_endpoint`` is a legal kind and is not written yet.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e5b1c8d24a70"
down_revision: str | None = "c3d8a1e57f04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KIND = sa.Enum(
    "email",
    "gps_point",
    "internal_endpoint",
    "software_version",
    "document_id",
    "device_serial",
    "author_string",
    name="correlationkind",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _KIND.create(bind, checkfirst=True)
        kind_type: sa.types.TypeEngine[str] = _KIND
    else:
        kind_type = sa.String()
    op.create_table(
        "value_entity",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("kind", kind_type, nullable=False),
        sa.Column("value_hash", sa.String(), nullable=False),
        sa.Column("value_norm", sa.Text(), nullable=False),
        sa.Column("first_seen_run_id", sa.String(), nullable=False),
        sa.Column("occurrences", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["first_seen_run_id"], ["run.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "value_hash", name="uq_value_entity_kind_hash"),
    )
    op.create_index("ix_value_entity_kind", "value_entity", ["kind"])
    op.create_index("ix_value_entity_value_hash", "value_entity", ["value_hash"])
    op.create_index("ix_value_entity_first_seen_run_id", "value_entity", ["first_seen_run_id"])
    op.create_table(
        "asset_value",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("asset_id", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("namespace", sa.String(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["asset_id"], ["asset.id"]),
        sa.ForeignKeyConstraint(["entity_id"], ["value_entity.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "asset_id", "entity_id", "namespace", "key", name="uq_asset_value_provenance"
        ),
    )
    op.create_index("ix_asset_value_asset_id", "asset_value", ["asset_id"])
    op.create_index("ix_asset_value_entity_id", "asset_value", ["entity_id"])


def downgrade() -> None:
    op.drop_index("ix_asset_value_entity_id", table_name="asset_value")
    op.drop_index("ix_asset_value_asset_id", table_name="asset_value")
    op.drop_table("asset_value")
    op.drop_index("ix_value_entity_first_seen_run_id", table_name="value_entity")
    op.drop_index("ix_value_entity_value_hash", table_name="value_entity")
    op.drop_index("ix_value_entity_kind", table_name="value_entity")
    op.drop_table("value_entity")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _KIND.drop(bind, checkfirst=True)
