"""TASK-46: filter indexes for global search

Revision ID: d4e8a2b91c07
Revises: c9e4b2a17d03
Create Date: 2026-11-12 20:00:00.000000

SQLite bootstrap creates the same indexes with CREATE INDEX IF NOT EXISTS.
"""
from collections.abc import Sequence

from alembic import op

revision: str = "d4e8a2b91c07"
down_revision: str | None = "c9e4b2a17d03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS ix_finding_finding_type ON finding (finding_type)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_finding_created_at_id ON finding (created_at DESC, id DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_raw_metadata_item_namespace ON raw_metadata_item (namespace)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_finding_finding_type")
    op.execute("DROP INDEX IF EXISTS ix_finding_created_at_id")
    op.execute("DROP INDEX IF EXISTS ix_raw_metadata_item_namespace")
