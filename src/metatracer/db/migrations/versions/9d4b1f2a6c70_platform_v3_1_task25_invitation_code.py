"""platform v3.1: invitation_code (TASK-25)

Revision ID: 9d4b1f2a6c70
Revises: 77f92328cc8e
Create Date: 2026-09-19 21:30:00.000000

Hand-finished following the Eje C migration style: one new table for the
single-use invitation codes. Only the SHA-256 of each code is persisted
(never the plaintext). FK actions (security review 2026-09-19): deleting a
user CASCADE-deletes the invitations they created — outstanding invitations
must not outlive their creator — and SET NULLs the ``used_by`` audit trail
of codes they redeemed (the row itself stays, ``used_at`` keeps the record).
``user_session`` cascades instead because sessions are meaningless without
their user.
"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = '9d4b1f2a6c70'
down_revision: str | None = '77f92328cc8e'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'invitation_code',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('code_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column(
            'role',
            sa.Enum('operator', 'viewer', name='userrole'),
            nullable=False,
        ),
        sa.Column('created_by', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('used_by', sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['created_by'],
            ['user.id'],
            name='invitation_code_created_by_fkey',
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(
            ['used_by'],
            ['user.id'],
            name='invitation_code_used_by_fkey',
            ondelete='SET NULL',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_invitation_code_code_hash'), 'invitation_code', ['code_hash'], unique=True
    )
    op.create_index(op.f('ix_invitation_code_created_by'), 'invitation_code', ['created_by'])


def downgrade() -> None:
    op.drop_index(op.f('ix_invitation_code_created_by'), table_name='invitation_code')
    op.drop_index(op.f('ix_invitation_code_code_hash'), table_name='invitation_code')
    op.drop_table('invitation_code')
    # Reused enum: do NOT drop userrole (user still depends on it).
