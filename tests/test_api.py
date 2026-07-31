"""API tests using FastAPI's TestClient - a real HTTP-shaped test (request/
response bodies, status codes, headers), not a call directly into route
functions.

Repoints ai_wasteguard.db.SessionLocal's *bind* the same way
tests/test_db.py does, so this genuinely exercises the app's own session
configuration (expire_on_commit=False etc.) rather than a reimplementation.
"""
import hashlib
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select

from ai_wasteguard import db
from ai_wasteguard.models import User, UserRole


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


def _create_project(client, token, title="Pilot"):
    resp = client.post("/api/v1/projects", json={"title": title}, headers=_auth_headers(token))
    assert resp.status_code == 201
    return resp.json()["id"]


def test_full_site_event_sample_chain_via_api(client):
    _register(client)
    token = _login(client).json()["access_token"]
    project_id = _create_project(client, token)

    site_resp = client.post(
        f"/api/v1/projects/{project_id}/sites",
        json={"name": "Site A", "country": "South Africa"},
        headers=_auth_headers(token),
    )
    assert site_resp.status_code == 201
    site_id = site_resp.json()["id"]
    assert site_resp.json()["project_id"] == project_id

    sites_list = client.get(f"/api/v1/projects/{project_id}/sites", headers=_auth_headers(token))
    assert sites_list.status_code == 200
    assert [s["id"] for s in sites_list.json()] == [site_id]

    event_resp = client.post(
        f"/api/v1/sites/{site_id}/sampling-events",
        json={"collected_at": "2026-01-15T10:00:00Z", "sample_matrix": "influent"},
        headers=_auth_headers(token),
    )
    assert event_resp.status_code == 201
    event_id = event_resp.json()["id"]

    events_list = client.get(f"/api/v1/sites/{site_id}/sampling-events", headers=_auth_headers(token))
    assert [e["id"] for e in events_list.json()] == [event_id]

    sample_resp = client.post(
        f"/api/v1/sampling-events/{event_id}/samples",
        json={"sample_type": "composite", "replicate": 1, "lab_identifier": "LAB-001"},
        headers=_auth_headers(token),
    )
    assert sample_resp.status_code == 201
    sample_id = sample_resp.json()["id"]
    assert sample_resp.json()["analysis_status"] == "pending"

    samples_list = client.get(f"/api/v1/sampling-events/{event_id}/samples", headers=_auth_headers(token))
    assert [s["id"] for s in samples_list.json()] == [sample_id]


def test_duplicate_replicate_returns_409(client):
    _register(client)
    token = _login(client).json()["access_token"]
    project_id = _create_project(client, token)
    site_id = client.post(
        f"/api/v1/projects/{project_id}/sites", json={"name": "Site A"}, headers=_auth_headers(token)
    ).json()["id"]
    event_id = client.post(
        f"/api/v1/sites/{site_id}/sampling-events",
        json={"collected_at": "2026-01-15T10:00:00Z"},
        headers=_auth_headers(token),
    ).json()["id"]

    first = client.post(
        f"/api/v1/sampling-events/{event_id}/samples", json={"replicate": 1}, headers=_auth_headers(token)
    )
    assert first.status_code == 201

    second = client.post(
        f"/api/v1/sampling-events/{event_id}/samples", json={"replicate": 1}, headers=_auth_headers(token)
    )
    assert second.status_code == 409


def test_non_owner_creating_site_gets_404_not_403(client):
    """Ownership (404) is checked before role (403) - consistent with not
    leaking project existence to someone who can't see it, even when they'd
    also fail the role check."""
    _register(client, role="researcher", email="owner@example.com")
    owner_token = _login(client, email="owner@example.com").json()["access_token"]
    project_id = _create_project(client, owner_token)

    _register(client, role="viewer", email="viewer@example.com")
    viewer_token = _login(client, email="viewer@example.com").json()["access_token"]

    resp = client.post(
        f"/api/v1/projects/{project_id}/sites", json={"name": "Should not be created"}, headers=_auth_headers(viewer_token)
    )
    assert resp.status_code == 404


def _set_role(email: str, role_value: str) -> None:
    with db.get_session() as session:
        user = session.execute(select(User).where(User.email == email)).scalar_one()
        user.role = UserRole(role_value)


def test_role_denied_creating_site_on_a_project_the_caller_owns(client):
    """Isolates the 403 (role) branch from the 404 (ownership) branch
    tested elsewhere: every self-registerable role that can own a project
    (only Researcher) also happens to be permitted to manage sites, so this
    combination can't arise through ordinary registration - reached here by
    directly demoting the owner's role after project creation, same as a
    real admin might reassign someone from Researcher to Student."""
    _register(client, role="researcher", email="owner@example.com")
    owner_token = _login(client, email="owner@example.com").json()["access_token"]
    project_id = _create_project(client, owner_token)

    resp = client.post(
        f"/api/v1/projects/{project_id}/sites", json={"name": "Should be created"}, headers=_auth_headers(owner_token)
    )
    assert resp.status_code == 201  # sanity: still Researcher, still allowed

    _set_role("owner@example.com", "student")

    resp2 = client.post(
        f"/api/v1/projects/{project_id}/sites", json={"name": "Should not be created"}, headers=_auth_headers(owner_token)
    )
    assert resp2.status_code == 403


def test_site_not_owned_returns_404(client):
    _register(client, email="owner@example.com")
    owner_token = _login(client, email="owner@example.com").json()["access_token"]
    project_id = _create_project(client, owner_token)
    site_id = client.post(
        f"/api/v1/projects/{project_id}/sites", json={"name": "Site A"}, headers=_auth_headers(owner_token)
    ).json()["id"]

    _register(client, email="other@example.com")
    other_token = _login(client, email="other@example.com").json()["access_token"]

    resp = client.get(f"/api/v1/sites/{site_id}/sampling-events", headers=_auth_headers(other_token))
    assert resp.status_code == 404


def _create_sample_chain(client, token, project_id):
    site_id = client.post(
        f"/api/v1/projects/{project_id}/sites", json={"name": "Site A"}, headers=_auth_headers(token)
    ).json()["id"]
    event_id = client.post(
        f"/api/v1/sites/{site_id}/sampling-events",
        json={"collected_at": "2026-01-15T10:00:00Z"},
        headers=_auth_headers(token),
    ).json()["id"]
    sample_id = client.post(
        f"/api/v1/sampling-events/{event_id}/samples", json={"replicate": 1}, headers=_auth_headers(token)
    ).json()["id"]
    return sample_id


def test_upload_via_api_matches_recorded_checksum(client):
    _register(client)
    token = _login(client).json()["access_token"]
    project_id = _create_project(client, token)
    sample_id = _create_sample_chain(client, token, project_id)

    content = b"sample_id,value\n1,42\n"
    resp = client.post(
        f"/api/v1/samples/{sample_id}/uploads",
        files={"file": ("counts.csv", content, "text/csv")},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["original_filename"] == "counts.csv"
    assert body["size_bytes"] == len(content)
    assert body["checksum_sha256"] == hashlib.sha256(content).hexdigest()

    listing = client.get(f"/api/v1/samples/{sample_id}/uploads", headers=_auth_headers(token))
    assert listing.status_code == 200
    assert [u["id"] for u in listing.json()] == [body["id"]]


def test_upload_rejects_unsupported_extension(client):
    _register(client)
    token = _login(client).json()["access_token"]
    project_id = _create_project(client, token)
    sample_id = _create_sample_chain(client, token, project_id)

    resp = client.post(
        f"/api/v1/samples/{sample_id}/uploads",
        files={"file": ("malware.exe", b"data", "application/octet-stream")},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 400


def test_upload_to_sample_not_owned_returns_404(client):
    _register(client, email="owner@example.com")
    owner_token = _login(client, email="owner@example.com").json()["access_token"]
    project_id = _create_project(client, owner_token)
    sample_id = _create_sample_chain(client, owner_token, project_id)

    _register(client, email="other@example.com")
    other_token = _login(client, email="other@example.com").json()["access_token"]

    resp = client.post(
        f"/api/v1/samples/{sample_id}/uploads",
        files={"file": ("counts.csv", b"data", "text/csv")},
        headers=_auth_headers(other_token),
    )
    assert resp.status_code == 404


def test_upload_role_denied_after_demotion(client):
    _register(client, role="researcher", email="owner@example.com")
    owner_token = _login(client, email="owner@example.com").json()["access_token"]
    project_id = _create_project(client, owner_token)
    sample_id = _create_sample_chain(client, owner_token, project_id)

    _set_role("owner@example.com", "student")

    resp = client.post(
        f"/api/v1/samples/{sample_id}/uploads",
        files={"file": ("counts.csv", b"data", "text/csv")},
        headers=_auth_headers(owner_token),
    )
    assert resp.status_code == 403


def test_submit_job_via_api_and_poll_to_completion(client):
    _register(client)
    token = _login(client).json()["access_token"]
    project_id = _create_project(client, token)

    submit = client.post(
        f"/api/v1/projects/{project_id}/jobs", json={}, headers=_auth_headers(token)
    )
    assert submit.status_code == 201
    job = submit.json()
    assert job["status"] == "queued"
    job_id = job["id"]

    final_status = None
    for _ in range(60):
        time.sleep(1)
        job = client.get(f"/api/v1/jobs/{job_id}", headers=_auth_headers(token)).json()
        if job["status"] in ("completed", "failed"):
            final_status = job["status"]
            break
    assert final_status == "completed", f"job did not complete in time: {job}"
    assert job["error_message"] is None

    listing = client.get(f"/api/v1/projects/{project_id}/jobs", headers=_auth_headers(token)).json()
    assert [j["id"] for j in listing] == [job_id]


def _create_completed_job(client, token, project_id):
    job_id = client.post(
        f"/api/v1/projects/{project_id}/jobs", json={}, headers=_auth_headers(token)
    ).json()["id"]
    for _ in range(60):
        time.sleep(1)
        job = client.get(f"/api/v1/jobs/{job_id}", headers=_auth_headers(token)).json()
        if job["status"] in ("completed", "failed"):
            assert job["status"] == "completed", f"job did not complete: {job}"
            return job_id
    raise AssertionError("job did not reach a terminal state in time")


def test_job_not_owned_returns_404(client):
    _register(client, email="owner@example.com")
    owner_token = _login(client, email="owner@example.com").json()["access_token"]
    project_id = _create_project(client, owner_token)
    job_id = client.post(
        f"/api/v1/projects/{project_id}/jobs", json={}, headers=_auth_headers(owner_token)
    ).json()["id"]

    _register(client, email="other@example.com")
    other_token = _login(client, email="other@example.com").json()["access_token"]

    resp = client.get(f"/api/v1/jobs/{job_id}", headers=_auth_headers(other_token))
    assert resp.status_code == 404


def test_job_submission_role_denied_after_demotion(client):
    _register(client, role="researcher", email="owner@example.com")
    owner_token = _login(client, email="owner@example.com").json()["access_token"]
    project_id = _create_project(client, owner_token)

    _set_role("owner@example.com", "student")

    resp = client.post(
        f"/api/v1/projects/{project_id}/jobs", json={}, headers=_auth_headers(owner_token)
    )
    assert resp.status_code == 403


def test_dashboard_requires_authentication(client):
    resp = client.get("/api/v1/dashboard")
    assert resp.status_code == 401


def test_dashboard_reflects_real_state(client):
    _register(client)
    token = _login(client).json()["access_token"]

    empty = client.get("/api/v1/dashboard", headers=_auth_headers(token)).json()
    assert empty["active_projects"] == 0
    assert empty["approved_models"] == []

    project_id = _create_project(client, token)
    client.post(
        f"/api/v1/projects/{project_id}/sites", json={"name": "Site A"}, headers=_auth_headers(token)
    )

    after = client.get("/api/v1/dashboard", headers=_auth_headers(token)).json()
    assert after["active_projects"] == 1
    assert after["sites"] == 1
    actions = [e["action"] for e in after["recent_activity"]]
    assert "project.create" in actions
    assert "site.create" in actions


def test_dashboard_scoped_to_caller_only(client):
    _register(client, email="owner@example.com")
    owner_token = _login(client, email="owner@example.com").json()["access_token"]
    _create_project(client, owner_token)

    _register(client, email="other@example.com")
    other_token = _login(client, email="other@example.com").json()["access_token"]

    other_summary = client.get("/api/v1/dashboard", headers=_auth_headers(other_token)).json()
    assert other_summary["active_projects"] == 0


def test_generate_and_read_report_via_api(client):
    _register(client)
    token = _login(client).json()["access_token"]
    project_id = _create_project(client, token)
    client.post(f"/api/v1/projects/{project_id}/sites", json={"name": "Site A"}, headers=_auth_headers(token))

    generate = client.post(f"/api/v1/projects/{project_id}/reports", headers=_auth_headers(token))
    assert generate.status_code == 201
    report = generate.json()
    assert report["project_id"] == project_id
    assert report["report_type"] == "project_summary"

    listing = client.get(f"/api/v1/projects/{project_id}/reports", headers=_auth_headers(token))
    assert [r["id"] for r in listing.json()] == [report["id"]]

    content = client.get(f"/api/v1/reports/{report['id']}/content", headers=_auth_headers(token))
    assert content.status_code == 200
    assert "Site A" in content.text
    assert "Project summary report" in content.text


def test_report_not_owned_returns_404(client):
    _register(client, email="owner@example.com")
    owner_token = _login(client, email="owner@example.com").json()["access_token"]
    project_id = _create_project(client, owner_token)
    report_id = client.post(
        f"/api/v1/projects/{project_id}/reports", headers=_auth_headers(owner_token)
    ).json()["id"]

    _register(client, email="other@example.com")
    other_token = _login(client, email="other@example.com").json()["access_token"]

    resp = client.get(f"/api/v1/reports/{report_id}/content", headers=_auth_headers(other_token))
    assert resp.status_code == 404


def test_register_and_approve_model_via_api(client):
    _register(client, role="researcher", email="owner@example.com")
    owner_token = _login(client, email="owner@example.com").json()["access_token"]
    project_id = _create_project(client, owner_token)
    job_id = _create_completed_job(client, owner_token, project_id)

    register = client.post(
        f"/api/v1/projects/{project_id}/models",
        json={"job_id": job_id, "name": "RF-baseline"},
        headers=_auth_headers(owner_token),
    )
    assert register.status_code == 201
    model = register.json()
    assert model["approval_status"] == "draft"
    assert model["name"] == "RF-baseline"
    model_id = model["id"]

    listing = client.get(f"/api/v1/projects/{project_id}/models", headers=_auth_headers(owner_token))
    assert [m["id"] for m in listing.json()] == [model_id]

    # Researcher (not Administrator) cannot approve.
    denied = client.post(f"/api/v1/models/{model_id}/approve", headers=_auth_headers(owner_token))
    assert denied.status_code == 403

    _set_role("owner@example.com", "administrator")
    approve = client.post(f"/api/v1/models/{model_id}/approve", headers=_auth_headers(owner_token))
    assert approve.status_code == 200
    assert approve.json()["approval_status"] == "approved"
    assert approve.json()["approved_by"] is not None


def test_register_model_from_job_in_another_project_returns_404(client):
    _register(client, email="owner@example.com")
    owner_token = _login(client, email="owner@example.com").json()["access_token"]
    project_a = _create_project(client, owner_token, title="Project A")
    project_b = _create_project(client, owner_token, title="Project B")
    job_id = _create_completed_job(client, owner_token, project_a)

    resp = client.post(
        f"/api/v1/projects/{project_b}/models",
        json={"job_id": job_id},
        headers=_auth_headers(owner_token),
    )
    assert resp.status_code == 404


def test_model_not_owned_cannot_be_approved(client):
    _register(client, role="researcher", email="owner@example.com")
    owner_token = _login(client, email="owner@example.com").json()["access_token"]
    project_id = _create_project(client, owner_token)
    job_id = _create_completed_job(client, owner_token, project_id)
    model_id = client.post(
        f"/api/v1/projects/{project_id}/models",
        json={"job_id": job_id},
        headers=_auth_headers(owner_token),
    ).json()["id"]

    _register(client, role="researcher", email="other@example.com")
    other_token = _login(client, email="other@example.com").json()["access_token"]
    _set_role("other@example.com", "administrator")

    resp = client.post(f"/api/v1/models/{model_id}/approve", headers=_auth_headers(other_token))
    assert resp.status_code == 404
