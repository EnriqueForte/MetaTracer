"""fase 3: finding types internal_endpoint and cloud_storage

Revision ID: f6a2d9c15b81
Revises: e5b1c8d24a70
Create Date: 2026-10-29 22:20:00.000000

Adds two labels to the Postgres ``findingtype`` enum. SQLite stores the
column as text, so it needs no DDL. The labels cannot be dropped cleanly;
downgrade leaves them in place.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f6a2d9c15b81"
down_revision: str | None = "e5b1c8d24a70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE findingtype ADD VALUE IF NOT EXISTS 'internal_endpoint'")
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE findingtype ADD VALUE IF NOT EXISTS 'cloud_storage'")


def downgrade() -> None:
    pass
