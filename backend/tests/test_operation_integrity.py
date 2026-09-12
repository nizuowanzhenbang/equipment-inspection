"""操作票回归：角色、顺序、失败阻断、持久化及草稿数据净化。"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app
from app.database import Base
from app.api.deps import get_db, get_current_user
from app.config import settings
from app.models.ticket import OperationTicket, OperationTicketStatus
from app.models.user import User, UserRole


@pytest.fixture
def context(monkeypatch):
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()
    user = User(username='test-inspector', role=UserRole.INSPECTOR, is_active=True)
    ticket = OperationTicket(ticket_no='OT-TEST-1', title='模拟操作流程',
        status=OperationTicketStatus.EXECUTING,
        steps=[{'seq': 1, 'action': '模拟步骤一'}, {'seq': 2, 'action': '模拟步骤二'}])
    db.add(ticket)
    db.commit()
    ticket_id = ticket.id
    monkeypatch.setattr(settings, 'SIGNATURE_REQUIRE_PASSWORD', False)
    def get_test_db():
        yield db
    app.dependency_overrides[get_db] = get_test_db
    app.dependency_overrides[get_current_user] = lambda: user
    try:
        yield TestClient(app), db, ticket_id, user
    finally:
        app.dependency_overrides.clear()
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def execute(client, tid, seq, result='PASS'):
    return client.post(f'/api/operation-tickets/{tid}/execute-step', json={'seq': seq, 'result': result})


def persisted(db, tid):
    db.expire_all()
    return db.get(OperationTicket, tid)


def test_steps_are_persisted_and_only_all_pass_completes(context):
    client, db, tid, _ = context
    assert execute(client, tid, 1).status_code == 200
    ticket = persisted(db, tid)
    assert ticket.steps[0]['result'] == 'PASS'
    assert ticket.steps[0]['executed_by'] == 'test-inspector'
    assert ticket.steps[0]['sig_hash']
    assert ticket.status == OperationTicketStatus.EXECUTING
    assert execute(client, tid, 2).json()['data']['all_done'] is True
    assert persisted(db, tid).status == OperationTicketStatus.COMPLETED
    assert [s['stage'] for s in ticket.signatures] == ['step-1', 'step-2', 'complete']


def test_fail_is_persisted_blocks_later_steps_and_cannot_be_overwritten(context):
    client, db, tid, _ = context
    assert execute(client, tid, 1, 'FAIL').json()['data']['all_done'] is False
    assert execute(client, tid, 2).status_code == 409
    assert execute(client, tid, 1).status_code == 409
    ticket = persisted(db, tid)
    assert ticket.steps[0]['result'] == 'FAIL'
    assert ticket.status == OperationTicketStatus.EXECUTING
    assert ticket.completed_at is None
    assert len(ticket.signatures) == 1


def test_last_step_failure_does_not_complete(context):
    client, db, tid, _ = context
    assert execute(client, tid, 1).status_code == 200
    assert execute(client, tid, 2, 'FAIL').json()['data']['all_done'] is False
    assert persisted(db, tid).status == OperationTicketStatus.EXECUTING


def test_cannot_skip_or_overwrite_steps(context):
    client, db, tid, _ = context
    assert execute(client, tid, 2).status_code == 409
    assert execute(client, tid, 1).status_code == 200
    assert execute(client, tid, 1, 'FAIL').status_code == 409
    assert persisted(db, tid).steps[0]['result'] == 'PASS'


@pytest.mark.parametrize('result', ['OK', '', 'pass', 'SKIPPED'])
def test_invalid_result_is_rejected(context, result):
    client, db, tid, _ = context
    assert execute(client, tid, 1, result).status_code == 422
    assert not persisted(db, tid).steps[0].get('result')


def test_viewer_cannot_execute(context):
    client, db, tid, user = context
    user.role = UserRole.VIEWER
    assert execute(client, tid, 1).status_code == 403
    assert not persisted(db, tid).steps[0].get('result')


def test_draft_input_cannot_forge_execution(context):
    client, db, _, _ = context
    response = client.post('/api/operation-tickets', json={'title': '模拟草稿', 'steps': [
        {'seq': 1, 'action': '模拟步骤', 'result': 'PASS', 'executed_by': 'admin', 'sig_hash': 'forged'}]})
    assert response.status_code == 200
    ticket = persisted(db, response.json()['data']['id'])
    assert ticket.steps[0]['result'] is None
    assert ticket.steps[0]['executed_by'] is None
    assert 'sig_hash' not in ticket.steps[0]


@pytest.mark.parametrize('steps', [[], None, [{'seq': 2, 'action': '跳号'}],
    [{'seq': 1, 'action': 'a'}, {'seq': 1, 'action': '重复'}], [{'action': ' '}], [{'seq': True, 'action': 'a'}]])
def test_invalid_draft_steps_rejected(context, steps):
    client, _, _, _ = context
    assert client.post('/api/operation-tickets', json={'title': '模拟草稿', 'steps': steps}).status_code == 400


def test_draft_update_cannot_inject_results_or_remove_steps(context):
    client, db, tid, _ = context
    ticket = db.get(OperationTicket, tid)
    ticket.status = OperationTicketStatus.DRAFT
    db.commit()
    response = client.put(f'/api/operation-tickets/{tid}', json={'steps': [{'action': '新步骤', 'result': 'PASS'}]})
    assert response.status_code == 200
    assert persisted(db, tid).steps[0]['result'] is None
    assert client.put(f'/api/operation-tickets/{tid}', json={'steps': None}).status_code == 400
