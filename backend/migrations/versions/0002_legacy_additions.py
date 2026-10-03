"""Normalize only the documented missing legacy columns and index."""
from alembic import op
import sqlalchemy as sa

revision = '0002_legacy_additions'
down_revision = '0001_frozen_baseline'
branch_labels = None
depends_on = None


def upgrade():
    connection = op.get_bind()
    for table in ('work_tickets', 'operation_tickets'):
        columns = {c['name'] for c in sa.inspect(connection).get_columns(table)}
        if 'signatures' not in columns:
            op.add_column(table, sa.Column('signatures', sa.JSON(), nullable=True))
    indexes = {i['name'] for i in sa.inspect(connection).get_indexes('inspection_records')}
    if 'uq_inspection_record_task_point' not in indexes:
        op.create_index('uq_inspection_record_task_point', 'inspection_records', ['task_id', 'point_id'], unique=True)


def downgrade():
    raise RuntimeError('Destructive downgrade is disabled; restore a verified backup into a separate database')
