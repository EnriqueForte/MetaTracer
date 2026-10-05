"""platform v3.2: keyset index on run.started_at (TASK-33)

Revision ID: c4a8e1b90f22
Revises: b7e2c91a4d18
Create Date: 2026-10-05 20:00:00.000000

History pagination orders by ``started_at DESC, id DESC``. SQLite bootstrap
creates the same index with ``CREATE INDEX IF NOT EXISTS``.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "c4a8e1b90f22"
down_revision: str | None = "b7e2c91a4d18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_run_started_at_id ON run (started_at DESC, id DESC)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_run_started_at_id")
