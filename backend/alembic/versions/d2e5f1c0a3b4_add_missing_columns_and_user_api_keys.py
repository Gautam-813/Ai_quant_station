"""Add missing columns to chat_memories + create user_api_keys table

Revision ID: d2e5f1c0a3b4
Revises: 8998f3c4fcc2
Create Date: 2026-05-30

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd2e5f1c0a3b4'
down_revision = '8998f3c4fcc2'
branch_labels = None
depends_on = None


def upgrade():
    # Add missing columns to chat_memories
    with op.batch_alter_table('chat_memories', schema=None) as batch_op:
        batch_op.add_column(sa.Column('reasoning', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('provider', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('model', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('tokens_used', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('latency_ms', sa.Integer(), nullable=True))

    # Create user_api_keys table
    op.create_table(
        'user_api_keys',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(), nullable=False),
        sa.Column('encrypted_key', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(('user_id',), ('users.id',), ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('user_api_keys', schema=None) as batch_op:
        batch_op.create_index('ix_user_api_keys_user_id', ['user_id'])


def downgrade():
    with op.batch_alter_table('user_api_keys', schema=None) as batch_op:
        batch_op.drop_index('ix_user_api_keys_user_id')
    op.drop_table('user_api_keys')

    with op.batch_alter_table('chat_memories', schema=None) as batch_op:
        batch_op.drop_column('latency_ms')
        batch_op.drop_column('tokens_used')
        batch_op.drop_column('model')
        batch_op.drop_column('provider')
        batch_op.drop_column('reasoning')
