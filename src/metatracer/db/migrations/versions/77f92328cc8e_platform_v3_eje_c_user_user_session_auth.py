"""platform v3 Eje C: user + user_session (auth)

Revision ID: 77f92328cc8e
Revises: f3c8525d72b2
Create Date: 2026-09-18 12:52:21.087775

Hand-finished from the autogenerate diff (the packaged programmatic env does
not drive ``alembic revision --autogenerate``; the diff was computed against
a scratch database at the previous head and the DDL written here — the
columns/types are exactly what ``compare_metadata`` reported).
"""
from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision: str = '77f92328cc8e'
down_revision: str | None = 'f3c8525d72b2'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'user',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('username', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('password_hash', sa.Text(), nullable=False),
        sa.Column(
            'role',
            sa.Enum('operator', 'viewer', name='userrole'),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_user_username'), 'user', ['username'], unique=True)

    op.create_table(
        'user_session',
        sa.Column('id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('user_id', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('token_hash', sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['user.id'],
            name='user_session_user_id_fkey',
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_user_session_token_hash'), 'user_session', ['token_hash'], unique=True
    )
    op.create_index(op.f('ix_user_session_user_id'), 'user_session', ['user_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_user_session_user_id'), table_name='user_session')
    op.drop_index(op.f('ix_user_session_token_hash'), table_name='user_session')
    op.drop_table('user_session')
    op.drop_index(op.f('ix_user_username'), table_name='user')
    op.drop_table('user')
    sa.Enum(name='userrole').drop(op.get_bind(), checkfirst=True)
