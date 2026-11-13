"""task-49: finding type secret

Revision ID: e7b3c4d15a92
Revises: d4e8a2b91c07
Create Date: 2026-11-13 19:40:00.000000

Adds ``secret`` to the Postgres ``findingtype`` enum. SQLite stores the
column as text, so it needs no DDL. The label cannot be dropped cleanly;
downgrade leaves it in place.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "e7b3c4d15a92"
down_revision: str | None = "d4e8a2b91c07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE findingtype ADD VALUE IF NOT EXISTS 'secret'")


def downgrade() -> None:
    pass
