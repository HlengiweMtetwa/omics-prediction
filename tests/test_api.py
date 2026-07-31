"""API tests using FastAPI's TestClient - a real HTTP-shaped test (request/
response bodies, status codes, headers), not a call directly into route
functions.

Repoints ai_wasteguard.db.SessionLocal's *bind* the same way
tests/test_db.py does, so this genuinely exercises the app's own session
configuration (expire_on_commit=False etc.) rather than a reimplementation.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from ai_wasteguard import db


@pytest.fixture()
def client(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'api_test.db'}", connect_args={"check_same_thread": False}, future=True
    )
    db.Base.metadata.create_all(engine)
    original_bind = db.SessionLocal.kw.get("bind")
    db.SessionLocal.configure(bind=engine)
    try:
        from api.main import app

        with TestClient(app) as c:
            yield c
    finally:
        db.SessionLocal.configure(bind=original_bind)


def _register(client, email="jane@example.com", role="researcher"):
    return client.post(
        "/api/v1/auth/register",
        json={
            "full_name": "Jane Doe",
            "email": email,
            "password": "correct-password",
            "institution": "Test University",
            "role": role,
        },
    )


def _login(client, email="jane@example.com"):
    return client.post("/api/v1/auth/login", json={"email": email, "password": "correct-password"})


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def test_health(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_register_login_me_flow(client):
    reg = _register(client)
    assert reg.status_code == 201
    body = reg.json()
    assert body["email"] == "jane@example.com"
    assert "password" not in body
    assert "password_hash" not in body

    login = _login(client)
    assert login.status_code == 200
    token = login.json()["access_token"]

    me = client.get("/api/v1/auth/me", headers=_auth_headers(token))
    assert me.status_code == 200
    assert me.json()["email"] == "jane@example.com"


def test_duplicate_registration_rejected(client):
    _register(client)
    resp = _register(client)
    assert resp.status_code == 400


def test_administrator_role_not_self_registerable_via_api(client):
    resp = _register(client, role="administrator")
    assert resp.status_code == 400


def test_wrong_password_rejected(client):
    _register(client)
    resp = client.post("/api/v1/auth/login", json={"email": "jane@example.com", "password": "wrong-password"})
    assert resp.status_code == 401


def test_projects_endpoint_requires_authentication(client):
    resp = client.get("/api/v1/projects")
    assert resp.status_code == 401

    resp2 = client.get("/api/v1/projects", headers=_auth_headers("not-a-real-token"))
    assert resp2.status_code == 401


def test_create_and_list_projects(client):
    _register(client)
    token = _login(client).json()["access_token"]

    create = client.post(
        "/api/v1/projects", json={"title": "Wastewater AMR Pilot"}, headers=_auth_headers(token)
    )
    assert create.status_code == 201
    project_id = create.json()["id"]

    listing = client.get("/api/v1/projects", headers=_auth_headers(token))
    assert listing.status_code == 200
    assert [p["id"] for p in listing.json()] == [project_id]

    fetched = client.get(f"/api/v1/projects/{project_id}", headers=_auth_headers(token))
    assert fetched.status_code == 200
    assert fetched.json()["title"] == "Wastewater AMR Pilot"


def test_viewer_role_cannot_create_project_via_api(client):
    _register(client, role="viewer")
    token = _login(client).json()["access_token"]

    resp = client.post("/api/v1/projects", json={"title": "Should not be created"}, headers=_auth_headers(token))
    assert resp.status_code == 403


def test_project_not_owned_returns_404_not_403(client):
    """Avoids leaking project-id existence to non-owners, same principle as
    the enumeration-safe login error."""
    _register(client, email="owner@example.com")
    owner_token = _login(client, email="owner@example.com").json()["access_token"]
    created = client.post(
        "/api/v1/projects", json={"title": "Owner's project"}, headers=_auth_headers(owner_token)
    )
    project_id = created.json()["id"]

    _register(client, email="other@example.com")
    other_token = _login(client, email="other@example.com").json()["access_token"]

    resp = client.get(f"/api/v1/projects/{project_id}", headers=_auth_headers(other_token))
    assert resp.status_code == 404
