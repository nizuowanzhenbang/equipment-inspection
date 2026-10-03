"""Freeze keyed purchase receipts without rewriting historical movements."""
from alembic import op
import sqlalchemy as sa

revision = '0003_purchase_receipts'
down_revision = '0002_legacy_additions'
branch_labels = None
depends_on = None


def upgrade():
    # Preflight has validated an existing unversioned current ORM table.
    if 'purchase_receipts' in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        'purchase_receipts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('purchase_request_id', sa.Integer(), nullable=False),
        sa.Column('request_id', sa.String(36), nullable=False),
        sa.Column('actor_id', sa.Integer(), nullable=False),
        sa.Column('qty', sa.Numeric(10, 2), nullable=False),
        sa.Column('movement_id', sa.Integer(), nullable=False),
        sa.Column('stock_qty_after', sa.Numeric(10, 2), nullable=False),
        sa.Column('status_after', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['purchase_request_id'], ['purchase_requests.id']),
        sa.ForeignKeyConstraint(['actor_id'], ['users.id']),
        sa.ForeignKeyConstraint(['movement_id'], ['stock_movements.id']),
        sa.UniqueConstraint('purchase_request_id', 'request_id', name='uq_purchase_receipt_request'),
        sa.UniqueConstraint('movement_id', name='uq_purchase_receipt_movement'),
    )


def downgrade():
    raise RuntimeError('Destructive downgrade is disabled; restore a verified backup into a separate database')
