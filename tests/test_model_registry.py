import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai_wasteguard import audit, auth, jobs, model_registry, registry
from ai_wasteguard.db import Base
from ai_wasteguard.models import ModelApprovalStatus, UserRole


@pytest.fixture()
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    with Session() as s:
        yield s


@pytest.fixture()
def completed_job(session, tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    user = auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password")
    session.flush()
    project = registry.create_project(session, user.id, "Pilot")
    session.commit()
    job = jobs.create_job(session, project.id, user.id)
    session.commit()
    jobs.execute_job(session, job.id)
    return job, user


def test_register_model_from_completed_job(session, completed_job):
    job, user = completed_job
    model = model_registry.register_model_from_job(session, job.id, user.id)
    session.commit()

    assert model.approval_status == ModelApprovalStatus.DRAFT
    assert model.algorithm == "RandomForestClassifier"
    assert "Accuracy" in model.metrics
    assert "synthetic data" in model.prohibited_use.lower()
    assert model in model_registry.list_models_for_project(session, job.project_id)


def test_cannot_register_model_from_incomplete_job(session, tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    user = auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password")
    session.flush()
    project = registry.create_project(session, user.id, "Pilot")
    session.commit()
    job = jobs.create_job(session, project.id, user.id)  # still QUEUED
    session.commit()

    with pytest.raises(model_registry.ModelRegistrationError):
        model_registry.register_model_from_job(session, job.id, user.id)


def test_cannot_register_model_from_failed_job(session, tmp_path, monkeypatch):
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(jobs, "PIPELINE_SCRIPTS", ["does_not_exist.py"])
    user = auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password")
    session.flush()
    project = registry.create_project(session, user.id, "Pilot")
    session.commit()
    job = jobs.create_job(session, project.id, user.id)
    session.commit()
    jobs.execute_job(session, job.id)

    with pytest.raises(model_registry.ModelRegistrationError):
        model_registry.register_model_from_job(session, job.id, user.id)


def test_approve_model_records_approver_and_timestamp(session, completed_job):
    job, user = completed_job
    admin = auth.register_user(session, "Admin", "admin@example.com", "correct-password", role=UserRole.ADMINISTRATOR)
    session.flush()
    model = model_registry.register_model_from_job(session, job.id, user.id)
    session.commit()

    approved = model_registry.approve_model(session, model.id, admin.id)
    session.commit()

    assert approved.approval_status == ModelApprovalStatus.APPROVED
    assert approved.approved_by == admin.id
    assert approved.approved_at is not None


def test_model_registration_is_audited(session, completed_job):
    job, user = completed_job
    model_registry.register_model_from_job(session, job.id, user.id)
    session.commit()

    actions = [e.action for e in audit.list_events_for_actor(session, user.id)]
    assert "model.register" in actions
