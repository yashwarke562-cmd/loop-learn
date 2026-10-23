import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def make_client(monkeypatch):
    def _make(**env):
        monkeypatch.setenv("TEACHER_PIN", "4321")
        monkeypatch.setenv("ID_SALT", "test-salt")
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)
        for k, v in env.items():
            monkeypatch.setenv(k, str(v))
        from app.main import create_app
        return TestClient(create_app())
    return _make


@pytest.fixture
def client(make_client):
    return make_client()


def student(name="maya"):
    return {"X-Demo-User": name, "X-Demo-Role": "student"}


def teacher(pin="4321"):
    return {"X-Demo-User": "ms_rao", "X-Demo-Role": "teacher", "X-Demo-Pin": pin}
