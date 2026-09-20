"""演示命令需真实跑通且不能使用调用方的数据库。"""
import json
import os
from pathlib import Path
import subprocess
import sys


SCRIPT = Path(__file__).resolve().parents[1] / 'interview_demo.py'


def test_demo_is_repeatable_and_ignores_existing_database(tmp_path):
    existing = tmp_path / 'existing.db'
    existing.write_bytes(b'untouched database sentinel')
    env = {**os.environ, 'DATABASE_URL': f'sqlite:///{existing.as_posix()}',
           'SCHEDULER_ENABLED': 'true', 'SAFETY_SYSTEM_URL': 'http://127.0.0.1:1',
           'UPLOAD_DIR': str(tmp_path / 'must-not-create')}
    for index in range(2):
        output = tmp_path / f'evidence-{index}.json'
        run = subprocess.run([sys.executable, str(SCRIPT), '--output', str(output)],
                             cwd=tmp_path, env=env, capture_output=True, text=True,
                             encoding='utf-8', timeout=60)
        assert run.returncode == 0, run.stderr
        report = json.loads(output.read_text(encoding='utf-8'))
        assert report['status'] == 'passed'
        assert report['scenario'] == 'inspection-to-repair-v1'
        assert len(report['checks']) >= 15
        assert all(check['passed'] for check in report['checks'])
        assert report['result']['task_status'] == 'COMPLETED'
        assert report['result']['defect_status'] == 'CLOSED'
        assert report['result']['health_scores'] == [100, 92, 92, 98]
        assert report['result']['record_count'] == 1
        assert report['result']['defect_count'] == 1
        assert 'access_token' not in output.read_text(encoding='utf-8')
        assert existing.read_bytes() == b'untouched database sentinel'
        assert not (tmp_path / 'must-not-create').exists()


def test_demo_refuses_to_overwrite_report(tmp_path):
    output = tmp_path / 'existing.json'
    output.write_text('keep this report', encoding='utf-8')
    run = subprocess.run([sys.executable, str(SCRIPT), '--output', str(output)],
                         cwd=tmp_path, capture_output=True, timeout=60)
    assert run.returncode != 0
    assert output.read_text(encoding='utf-8') == 'keep this report'
