"""fase 2: run ingestion stats (crawl budget + coverage counters)

Revision ID: a8e3f1c47b90
Revises: d1f7a3c5e9b4
Create Date: 2026-10-26 00:30:00.000000

Adds ``run.ingestion_stats``: a JSON snapshot of the crawl budget that applied
to the run plus the counters it actually reached (pages, queued assets, bytes,
elapsed) and the limits it hit. It is what lets the coverage view and the report
say *why* a crawl stopped instead of implying the target was exhausted.

Nullable on purpose: rows recorded before this revision have no snapshot, and
the API reports ``counters_recorded=false`` for them rather than inventing a
zero. SQLite picks the column up through the additive bootstrap in ``init_db``.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a8e3f1c47b90"
down_revision: str | None = "d1f7a3c5e9b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("run", sa.Column("ingestion_stats", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("run", "ingestion_stats")
