"""Add isolated allocation and immutable delivery state without changing old rows."""
from alembic import op
import sqlalchemy as sa

revision = '0004_reliability_state'
down_revision = '0003_purchase_receipts'
branch_labels = None
depends_on = None


def upgrade():
    tables = sa.inspect(op.get_bind()).get_table_names()
    if 'purchase_number_sequences' not in tables:
        op.create_table('purchase_number_sequences',
                        sa.Column('day', sa.String(8), nullable=False),
                        sa.Column('last_value', sa.Integer(), nullable=False),
                        sa.PrimaryKeyConstraint('day'))
    if 'safety_outbox' not in tables:
        op.create_table('safety_outbox',
                        sa.Column('defect_id', sa.Integer(), autoincrement=False, nullable=False),
                        sa.Column('payload', sa.JSON(), nullable=False),
                        sa.Column('created_at', sa.DateTime(), nullable=False),
                        sa.PrimaryKeyConstraint('defect_id'),
                        sa.ForeignKeyConstraint(['defect_id'], ['defects.id']))


def downgrade():
    raise RuntimeError('Destructive downgrade is disabled; restore a verified backup separately')
