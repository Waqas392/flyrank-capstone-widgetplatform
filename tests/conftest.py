import itertools

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

_ip_counter = itertools.count(1)


def fresh_ip() -> str:
    """Every test request gets its own client IP so per-IP rate limits don't bleed between tests."""
    n = next(_ip_counter)
    return f"203.0.{(n // 250) % 250}.{n % 250 + 1}"


@pytest.fixture()
def settings(tmp_path):
    return Settings(
        database_url=f"sqlite:///{tmp_path}/test.db",
        public_base_url="http://testserver",
        secret_key="test-secret",
        trust_proxy=True,
        run_worker=False,          # tests drive the job worker by hand -> deterministic
        job_backoff_base=0,        # retries are immediately due
        geo_mode="mock",
        debug_endpoints=True,
        min_fill_ms=1500,
    )


@pytest.fixture()
def app(settings):
    return create_app(settings)


@pytest.fixture()
def client(app):
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def ctx(app):
    return app.state.ctx


def register(client, email="owner@example.com", password="correct-horse-1"):
    r = client.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture()
def auth(client):
    return register(client)


@pytest.fixture()
def widget(client, auth):
    r = client.post("/api/widgets", headers=auth, json={"type": "contact_form", "title": "Contact us"})
    assert r.status_code == 201, r.text
    return r.json()


def submit(client, widget_id, data=None, ip=None, headers=None, **extra):
    body = {"widget_id": widget_id, "data": data if data is not None else {"name": "Ada", "email": "ada@example.com", "message": "Hello"}}
    body.update(extra)
    h = {"X-Forwarded-For": ip or fresh_ip(), "Origin": "http://localhost:5500"}
    h.update(headers or {})
    return client.post("/submissions", json=body, headers=h)
