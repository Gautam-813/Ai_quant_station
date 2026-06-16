"""Add Autopilot decision metadata

Revision ID: e4a7b9c2d1f3
Revises: d2e5f1c0a3b4
Create Date: 2026-06-16

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e4a7b9c2d1f3"
down_revision = "d2e5f1c0a3b4"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("autopilot_trades", schema=None) as batch_op:
        batch_op.add_column(sa.Column("market_regime", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("regime_details", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("prompt_tags", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("decision_score", sa.Float(), nullable=True))
        batch_op.add_column(sa.Column("decision_context", sa.JSON(), nullable=True))
        batch_op.create_index("ix_autopilot_trades_market_regime", ["market_regime"])


def downgrade():
    with op.batch_alter_table("autopilot_trades", schema=None) as batch_op:
        batch_op.drop_index("ix_autopilot_trades_market_regime")
        batch_op.drop_column("decision_context")
        batch_op.drop_column("decision_score")
        batch_op.drop_column("prompt_tags")
        batch_op.drop_column("regime_details")
        batch_op.drop_column("market_regime")
