"""fase 3: investigation group

Revision ID: c3d8a1e57f04
Revises: b7c2e9a41d08
Create Date: 2026-10-29 21:30:00.000000

Adds ``investigation`` and a nullable ``run.investigation_id``. A null value
means the run is ungrouped. The foreign key does not isolate tenants: every
reader of the install can still see every run. SQLite picks the table and
the column up through ``init_db`` (create_all + additive ALTER).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3d8a1e57f04"
down_revision: str | None = "b7c2e9a41d08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS = sa.Enum("open", "closed", name="investigationstatus")


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _STATUS.create(bind, checkfirst=True)
        status_type: sa.types.TypeEngine[str] = _STATUS
    else:
        status_type = sa.String()
    op.create_table(
        "investigation",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", status_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index("ix_investigation_name", "investigation", ["name"], unique=True)
    op.add_column("run", sa.Column("investigation_id", sa.String(), nullable=True))
    op.create_index("ix_run_investigation_id", "run", ["investigation_id"])
    op.create_foreign_key(
        "fk_run_investigation_id",
        "run",
        "investigation",
        ["investigation_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_run_investigation_id", "run", type_="foreignkey")
    op.drop_index("ix_run_investigation_id", table_name="run")
    op.drop_column("run", "investigation_id")
    op.drop_index("ix_investigation_name", table_name="investigation")
    op.drop_table("investigation")
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        _STATUS.drop(bind, checkfirst=True)
