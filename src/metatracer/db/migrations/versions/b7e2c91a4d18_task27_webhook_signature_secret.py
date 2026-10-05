"""platform v3.2: webhook HMAC secret stored for signing (TASK-27)

Revision ID: b7e2c91a4d18
Revises: 9d4b1f2a6c70
Create Date: 2026-10-03 20:00:00.000000

Adds nullable ``webhook_config.signature_secret`` (plaintext). SQLite picks
the same column up through the additive bootstrap in ``init_db``. Existing
rows keep ``signature_secret_hash`` only and stay unsigned until the operator
sets the secret again. The secret is never returned by the API.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e2c91a4d18"
down_revision: str | None = "9d4b1f2a6c70"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("webhook_config", sa.Column("signature_secret", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("webhook_config", "signature_secret")
