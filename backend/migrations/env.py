"""Only the preflighted application migration command may supply this connection."""
from alembic import context

connection = context.config.attributes.get('connection')
if connection is None or not context.config.attributes.get('preflight_passed'):
    raise RuntimeError('Use python -m app.migrate upgrade; direct unvalidated Alembic execution is disabled')
context.configure(connection=connection, transactional_ddl=True)
with context.begin_transaction():
    context.run_migrations()
