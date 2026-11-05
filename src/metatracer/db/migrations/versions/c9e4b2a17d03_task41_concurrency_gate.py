"""task 41: singleton concurrency gate

Revision ID: c9e4b2a17d03
Revises: b2d8f5c31e90
Create Date: 2026-11-05 23:20:00.000000

One-row table locked while a process counts open runs. SQLite creates it
through ``init_db``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c9e4b2a17d03"
down_revision: str | None = "b2d8f5c31e90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "concurrency_gate",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("INSERT INTO concurrency_gate (id) VALUES (1) ON CONFLICT DO NOTHING")


def downgrade() -> None:
    op.drop_table("concurrency_gate")
