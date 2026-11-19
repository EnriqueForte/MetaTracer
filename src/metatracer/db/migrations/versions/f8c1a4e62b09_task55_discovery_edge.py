"""TASK-55: discovery_edge for the live scan graph

Revision ID: f8c1a4e62b09
Revises: e7b3c4d15a92
Create Date: 2026-11-19 17:50:00.000000

Persists crawl and local-ingest parent→child URLs. SQLite also gets the
table via SQLModel ``create_all``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f8c1a4e62b09"
down_revision: str | None = "e7b3c4d15a92"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_KIND = sa.Enum(
    "page",
    "document",
    "script",
    "probe",
    "local",
    name="discoveryedgekind",
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _KIND.create(bind, checkfirst=True)
        kind_type: sa.types.TypeEngine[str] = _KIND
    else:
        kind_type = sa.String()
    op.create_table(
        "discovery_edge",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("from_url", sa.Text(), nullable=False),
        sa.Column("to_url", sa.Text(), nullable=False),
        sa.Column("kind", kind_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["run.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "from_url",
            "to_url",
            "kind",
            name="uq_discovery_edge_run_urls_kind",
        ),
    )
    op.create_index("ix_discovery_edge_run_id", "discovery_edge", ["run_id"])
    op.create_index(
        "ix_discovery_edge_run_id_created_at",
        "discovery_edge",
        ["run_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_discovery_edge_run_id_created_at", table_name="discovery_edge")
    op.drop_index("ix_discovery_edge_run_id", table_name="discovery_edge")
    op.drop_table("discovery_edge")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _KIND.drop(bind, checkfirst=True)
