"""在一次性数据库内运行真实登录与点检检修 API，输出可复核的演示报告。

仅作为独立命令运行；不提供远端地址或数据库参数。
"""
from contextlib import redirect_stdout
from datetime import datetime, timezone
import argparse
import json
import os
from pathlib import Path
import secrets
import sys
from tempfile import TemporaryDirectory


def run_scenario(client):
    checks = []

    def check(name, actual, expected):
        passed = actual == expected
        checks.append({'name': name, 'actual': actual, 'expected': expected, 'passed': passed})
        if not passed:
            raise RuntimeError(f'{name}: expected {expected!r}, got {actual!r}')

    # 使用应用启动时创建的演示账户，真实密码校验及 JWT 鉴权，不覆盖依赖。
    tokens = {}
    for role in ('admin', 'inspector', 'repairman', 'supervisor', 'viewer'):
        response = client.post('/api/auth/login', data={'username': role, 'password': role + '123'})
        check(f'{role} 登录', response.status_code, 200)
        tokens[role] = response.json()['access_token']

    def request(method, path, role='admin', body=None, expected=200):
        response = client.request(method, path, headers={'Authorization': f'Bearer {tokens[role]}'},
                                  **({'json': body} if body is not None else {}))
        if response.status_code != expected:
            raise RuntimeError(f'{method} {path} ({role}): expected HTTP {expected}, got {response.status_code}')
        return response.json().get('data') if expected == 200 else response.status_code

    equipment = request('POST', '/api/equipments', body={
        'name': '面试演示给水泵（模拟）', 'equipment_system': 'AUXILIARY', 'criticality': 'B'})
    eid = equipment['id']
    scores = [equipment['health_score']]
    check('初始健康度', scores[-1], 100)
    route = request('POST', '/api/routes', body={
        'name': '面试演示路线', 'points': [{'equipment_id': eid, 'check_items': [
            {'name': '轴承温度', 'type': 'number', 'unit': '℃', 'max': 80}]}]})
    task = request('POST', '/api/tasks/generate', body={
        'route_id': route['id'], 'scheduled_at': datetime.now(timezone.utc).isoformat(),
        'assigned_to': 'inspector'})
    task_path = f"/api/tasks/{task['id']}"
    request('POST', task_path + '/start', 'inspector')
    payload = {'point_id': route['points'][0]['id'], 'status': 'SEVERE',
               'readings': {'temperature': 95}, 'finding': '模拟：轴承温度异常升高'}
    check('只读账户不能录入', request('POST', task_path + '/records', 'viewer', payload, 403), 403)
    record = request('POST', task_path + '/records', 'inspector', payload)
    defect_path = f"/api/defects/{record['defect_id']}"
    defect = request('GET', defect_path)
    check('异常生成重大缺陷', defect['severity'], 'MAJOR')
    check('新缺陷状态', defect['status'], 'NEW')
    equipment = request('GET', f'/api/equipments/{eid}')
    scores.append(equipment['health_score'])
    check('严重异常切换检修状态', equipment['status'], 'MAINTENANCE')
    check('重大缺陷扣分一次', scores[-1], 92)

    replay = request('POST', task_path + '/records', 'inspector', payload)
    check('重传返回相同记录', replay['id'], record['id'])
    check('重传返回相同缺陷', replay['defect_id'], record['defect_id'])
    check('冲突重传被拒绝', request('POST', task_path + '/records', 'inspector',
          {**payload, 'finding': '不同内容'}, 409), 409)
    scores.append(request('GET', f'/api/equipments/{eid}')['health_score'])
    check('重传不重复扣分', scores[-1], 92)
    task = request('GET', task_path)
    check('任务完成', task['status'], 'COMPLETED')
    check('记录只有一份', len(task['records']), 1)
    check('冲突不改写原始发现', task['records'][0]['finding'], payload['finding'])
    defects = request('GET', f'/api/defects?equipment_id={eid}')
    check('缺陷只有一份', defects['total'], 1)
    check('点检员不能派工', request('POST', defect_path + '/assign', 'inspector',
          {'assigned_to': 'repairman'}, 403), 403)

    request('POST', defect_path + '/assign', 'supervisor', {'assigned_to': 'repairman'})
    check('主管派工', request('GET', defect_path)['status'], 'ASSIGNED')
    request('POST', defect_path + '/start-repair', 'repairman')
    check('维修开始', request('GET', defect_path)['status'], 'IN_REPAIR')
    request('POST', defect_path + '/repair', 'repairman', {'repair_notes': '模拟：补充润滑并试运'})
    check('维修提交', request('GET', defect_path)['status'], 'REPAIRED')
    request('POST', defect_path + '/verify', 'supervisor', {'pass_': False, 'verify_notes': '模拟：仍需复检'})
    check('驳回返回检修', request('GET', defect_path)['status'], 'IN_REPAIR')
    check('驳回不恢复健康度', request('GET', f'/api/equipments/{eid}')['health_score'], 92)
    request('POST', defect_path + '/repair', 'repairman', {'repair_notes': '模拟：复检温度正常'})
    request('POST', defect_path + '/verify', 'supervisor', {'pass_': True, 'verify_notes': '模拟验收通过'})
    defect = request('GET', defect_path)
    check('验收关闭', defect['status'], 'CLOSED')
    check('验收人被保存', defect['verified_by'], 'supervisor')
    check('关闭时间被保存', bool(defect['closed_at']), True)
    equipment = request('GET', f'/api/equipments/{eid}')
    scores.append(equipment['health_score'])
    check('无其他缺陷恢复运行', equipment['status'], 'RUNNING')
    check('验收回弹六分', scores[-1], 98)
    check('关闭后不能重复验收', request('POST', defect_path + '/verify', 'supervisor', {'pass_': True}, 400), 400)
    check('重复验收不重复回弹', request('GET', f'/api/equipments/{eid}')['health_score'], 98)
    audit = request('GET', '/api/audit?target_type=Defect')
    actions = [row['action'] for row in audit['items'] if row['target_id'] == defect['id']]
    for action in ('defect.assign', 'defect.verify_reject', 'defect.verify_pass'):
        check(f'审计记录 {action}', action in actions, True)

    return {'scenario': 'inspection-to-repair-v1', 'status': 'passed',
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'scope': '临时 SQLite、真实 JWT 和 API；模拟数据；未验证浏览器 UI 或生产部署',
            'checks': checks,
            'result': {'task_status': task['status'], 'defect_status': defect['status'],
                       'health_scores': scores, 'record_count': len(task['records']),
                       'defect_count': defects['total'], 'audit_actions': sorted(actions)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='保存 JSON 证据到新文件；已有文件不覆盖')
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.error('输出文件已存在，请指定新文件名')
    # 必须在导入 app/settings 之前强制隔离，覆盖 shell/.env 中的数据库和外部联动配置。
    with TemporaryDirectory(prefix='equipment-interview-') as directory:
        root = Path(directory)
        os.environ.update(DATABASE_URL=f'sqlite:///{(root / "demo.db").as_posix()}',
                          UPLOAD_DIR=str(root / 'uploads'), SCHEDULER_ENABLED='false',
                          SAFETY_SYSTEM_URL='', PROCUREMENT_SYSTEM_URL='', STORAGE_BACKEND='local',
                          SECRET_KEY=secrets.token_hex(32), DEBUG='false')
        with redirect_stdout(sys.stderr):
            from fastapi.testclient import TestClient
            from app.main import app
            from app.database import engine
            try:
                with TestClient(app) as client:
                    report = run_scenario(client)
            finally:
                engine.dispose()
        content = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
        if args.output:
            with args.output.open('x', encoding='utf-8') as output:
                output.write(content)
            print(f"PASS: {len(report['checks'])} checks; report: {args.output}")
        else:
            print(content, end='')


if __name__ == '__main__':
    main()
