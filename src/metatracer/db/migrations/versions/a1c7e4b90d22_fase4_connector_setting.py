"""fase 4: connector enablement

Revision ID: a1c7e4b90d22
Revises: f6a2d9c15b81
Create Date: 2026-10-29 23:00:00.000000

``connector_setting`` records whether a connector may send data. Missing
rows mean disabled. SQLite creates the table through ``init_db``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a1c7e4b90d22"
down_revision: str | None = "f6a2d9c15b81"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "connector_setting",
        sa.Column("connector_id", sa.String(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("connector_id"),
    )


def downgrade() -> None:
    op.drop_table("connector_setting")
