"""fase 2: skip_reason robots_disallow

Revision ID: b7c2e9a41d08
Revises: a8e3f1c47b90
Create Date: 2026-10-29 20:10:00.000000

Adds the courtesy label ``robots_disallow`` to the Postgres enum. A URL
matched by ``Disallow`` is stored as ``skipped`` with this reason and is not
requested. The value does not mean the URL is out of scope, absent, or unsafe.

SQLite stores ``skip_reason`` as text, so it needs no DDL. Postgres cannot
drop a single enum label; downgrade leaves the value in place, which is safe
because older code never writes it.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b7c2e9a41d08"
down_revision: str | None = "a8e3f1c47b90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    # ADD VALUE cannot always run inside the migration transaction.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE skipreason ADD VALUE IF NOT EXISTS 'robots_disallow'")


def downgrade() -> None:
    pass
