from tests.postgresql.test_backup_restore import backup_databases  # noqa: F401
from tests.test_recovered_workflow import recovered_workflow


def test_postgresql_recovered_workflow(backup_databases, tmp_path, monkeypatch):
    recovered_workflow(*backup_databases, tmp_path, monkeypatch)
