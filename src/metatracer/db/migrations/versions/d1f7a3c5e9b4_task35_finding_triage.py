"""platform v3.2: finding triage status (TASK-35)

Revision ID: d1f7a3c5e9b4
Revises: c4a8e1b90f22
Create Date: 2026-10-05 21:30:00.000000

Adds ``finding.triage_status`` (NOT NULL, default ``open``, indexed) plus the
nullable ``triage_note``, ``triaged_by`` and ``triaged_at``. SQLite picks the
same columns up through the additive bootstrap in ``init_db``.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d1f7a3c5e9b4"
down_revision: str | None = "c4a8e1b90f22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TRIAGE = sa.Enum("open", "confirmed", "false_positive", "fixed", name="triagestatus")


def upgrade() -> None:
    _TRIAGE.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "finding",
        sa.Column("triage_status", _TRIAGE, nullable=False, server_default="open"),
    )
    op.add_column("finding", sa.Column("triage_note", sa.Text(), nullable=True))
    op.add_column("finding", sa.Column("triaged_by", sa.String(), nullable=True))
    op.add_column("finding", sa.Column("triaged_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_finding_triage_status", "finding", ["triage_status"])


def downgrade() -> None:
    op.drop_index("ix_finding_triage_status", table_name="finding")
    op.drop_column("finding", "triaged_at")
    op.drop_column("finding", "triaged_by")
    op.drop_column("finding", "triage_note")
    op.drop_column("finding", "triage_status")
    _TRIAGE.drop(op.get_bind(), checkfirst=True)
