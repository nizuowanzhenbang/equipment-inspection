"""隔离导入和路由检查；不启动演示数据或后台调度器。"""
from fastapi.testclient import TestClient
from app.main import app


def test_openapi_is_available():
    response = TestClient(app).get('/openapi.json')
    assert response.status_code == 200
    assert '/api/auth/login' in response.json()['paths']


def test_password_hash_round_trip():
    from app.api.deps import hash_password, verify_password
    hashed = hash_password('maintenance-test-password')
    assert verify_password('maintenance-test-password', hashed)
    assert not verify_password('wrong-password', hashed)
