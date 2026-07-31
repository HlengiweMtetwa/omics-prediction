from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai_wasteguard import auth, dashboard, jobs, model_registry, registry
from ai_wasteguard.db import Base
from ai_wasteguard.models import JobStatus


@pytest.fixture()
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    with Session() as s:
        yield s


def test_empty_dashboard_for_new_user(session):
    user = auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password")
    session.commit()

    summary = dashboard.get_dashboard_summary(session, user.id)

    assert summary.active_projects == 0
    assert summary.sites == 0
    assert summary.samples == 0
    assert summary.jobs_queued == 0
    assert summary.approved_models == []


def test_counts_only_the_owners_own_data(session):
    owner = auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password")
    other = auth.register_user(session, "Other User", "other@example.com", "correct-password")
    session.flush()

    owner_project = registry.create_project(session, owner.id, "Owner Pilot")
    session.flush()
    registry.create_site(session, owner_project.id, "Owner Site")

    other_project = registry.create_project(session, other.id, "Other Pilot")
    session.flush()
    registry.create_site(session, other_project.id, "Other Site")
    registry.create_site(session, other_project.id, "Other Site 2")
    session.commit()

    summary = dashboard.get_dashboard_summary(session, owner.id)

    assert summary.active_projects == 1
    assert summary.sites == 1


def test_job_status_breakdown(session, tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    user = auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password")
    session.flush()
    project = registry.create_project(session, user.id, "Pilot")
    session.commit()

    queued_job = jobs.create_job(session, project.id, user.id)
    session.commit()
    completed_job = jobs.create_job(session, project.id, user.id)
    session.commit()
    jobs.execute_job(session, completed_job.id)

    summary = dashboard.get_dashboard_summary(session, user.id)

    assert summary.jobs_queued == 1
    assert summary.jobs_completed == 1
    assert summary.jobs_failed == 0


def test_only_approved_models_are_surfaced(session, tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    user = auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password")
    session.flush()
    project = registry.create_project(session, user.id, "Pilot")
    session.commit()
    job = jobs.create_job(session, project.id, user.id)
    session.commit()
    jobs.execute_job(session, job.id)
    model = model_registry.register_model_from_job(session, job.id, user.id)
    session.commit()

    summary_before = dashboard.get_dashboard_summary(session, user.id)
    assert summary_before.approved_models == []

    model_registry.approve_model(session, model.id, user.id)
    session.commit()

    summary_after = dashboard.get_dashboard_summary(session, user.id)
    assert [m.id for m in summary_after.approved_models] == [model.id]


def test_recent_activity_reflects_audit_log(session):
    user = auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password")
    session.commit()
    registry.create_project(session, user.id, "Pilot")
    session.commit()

    summary = dashboard.get_dashboard_summary(session, user.id)

    actions = [e.action for e in summary.recent_activity]
    assert "register.success" in actions
    assert "project.create" in actions
