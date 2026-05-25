"""add_revoked_tokens_and_position_audits

Revision ID: 8998f3c4fcc2
Revises: '78a4bf92898a'
Create Date: 2026-05-21 16:57:18.277809

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite


# revision identifiers, used by Alembic.
revision = '8998f3c4fcc2'
down_revision = '78a4bf92898a'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "revoked_tokens",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("token_jti", sa.String(), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_jti"),
    )
    with op.batch_alter_table("revoked_tokens", schema=None) as batch_op:
        batch_op.create_index("ix_revoked_tokens_expires_at", ["expires_at"], unique=False)
        batch_op.create_index("ix_revoked_tokens_token_jti", ["token_jti"], unique=True)

    op.create_table(
        "position_audits",
        sa.Column("id", sa.Integer(), nullable=False, autoincrement=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("mt5_ticket", sa.BigInteger(), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("symbol", sa.String(), nullable=False),
        sa.Column("original_sl", sa.Float(), nullable=True),
        sa.Column("original_tp", sa.Float(), nullable=True),
        sa.Column("new_sl", sa.Float(), nullable=True),
        sa.Column("new_tp", sa.Float(), nullable=True),
        sa.Column("close_volume", sa.Float(), nullable=True),
        sa.Column("close_price", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(("user_id",), ("users.id",), ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("position_audits", schema=None) as batch_op:
        batch_op.create_index("ix_position_audits_user_created", ["user_id", "created_at"], unique=False)
        batch_op.create_index("ix_position_audits_user_mt5_ticket", ["user_id", "mt5_ticket"], unique=False)


def downgrade():
    with op.batch_alter_table("position_audits", schema=None) as batch_op:
        batch_op.drop_index("ix_position_audits_user_mt5_ticket")
        batch_op.drop_index("ix_position_audits_user_created")
    op.drop_table("position_audits")
    with op.batch_alter_table("revoked_tokens", schema=None) as batch_op:
        batch_op.drop_index("ix_revoked_tokens_token_jti")
        batch_op.drop_index("ix_revoked_tokens_expires_at")
    op.drop_table("revoked_tokens")
