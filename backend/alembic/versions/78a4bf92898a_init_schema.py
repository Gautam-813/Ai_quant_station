"""Init schema: add composite indexes to chat_memories, autopilot_trades, calculation_history

Revision ID: 78a4bf92898a
Revises: None
Create Date: 2026-05-21 16:03:31

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '78a4bf92898a'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_index('ix_chat_memories_user_symbol', 'chat_memories', ['user_id', 'symbol'])
    op.create_index('ix_autopilot_trades_user_executed', 'autopilot_trades', ['user_id', 'executed_at'])
    op.create_index('ix_autopilot_trades_user_result', 'autopilot_trades', ['user_id', 'result'])
    op.create_index('ix_autopilot_trades_user_prompt', 'autopilot_trades', ['user_id', 'prompt_number'])
    op.create_index('ix_calc_history_user_created', 'calculation_history', ['user_id', 'created_at'])


def downgrade():
    op.drop_index('ix_calc_history_user_created', table_name='calculation_history')
    op.drop_index('ix_autopilot_trades_user_prompt', table_name='autopilot_trades')
    op.drop_index('ix_autopilot_trades_user_result', table_name='autopilot_trades')
    op.drop_index('ix_autopilot_trades_user_executed', table_name='autopilot_trades')
    op.drop_index('ix_chat_memories_user_symbol', table_name='chat_memories')
