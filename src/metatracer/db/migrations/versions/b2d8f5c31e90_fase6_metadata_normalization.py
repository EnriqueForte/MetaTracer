"""fase 6: original metadata value stays; a normalized reading is optional

Revision ID: b2d8f5c31e90
Revises: a1c7e4b90d22
Create Date: 2026-10-29 23:15:00.000000

Nullable columns. Rows written before this migration keep NULL, which the
explorer renders as "no normalized form", not as an empty reading.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2d8f5c31e90"
down_revision: str | None = "a1c7e4b90d22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("raw_metadata_item", sa.Column("value_normalized", sa.Text(), nullable=True))
    op.add_column("raw_metadata_item", sa.Column("normalized_kind", sa.String(), nullable=True))
    op.add_column("raw_metadata_item", sa.Column("timezone_status", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("raw_metadata_item", "timezone_status")
    op.drop_column("raw_metadata_item", "normalized_kind")
    op.drop_column("raw_metadata_item", "value_normalized")
