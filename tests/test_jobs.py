import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai_wasteguard import audit, auth, jobs, registry
from ai_wasteguard.db import Base
from ai_wasteguard.models import JobStatus


@pytest.fixture()
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    with Session() as s:
        yield s


@pytest.fixture()
def project_and_user(session):
    user = auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password")
    session.flush()
    project = registry.create_project(session, user.id, "Pilot")
    session.commit()
    return project, user


def test_create_job_starts_queued(session, project_and_user):
    project, user = project_and_user
    job = jobs.create_job(session, project.id, user.id)
    session.commit()
    assert job.status == JobStatus.QUEUED
    assert job in jobs.list_jobs_for_project(session, project.id)


def test_execute_job_runs_real_pipeline_and_completes(session, project_and_user, monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    project, user = project_and_user
    job = jobs.create_job(session, project.id, user.id)
    session.commit()

    result = jobs.execute_job(session, job.id)

    assert result.status == JobStatus.COMPLETED
    assert result.error_message is None
    assert result.started_at is not None
    assert result.completed_at is not None
    assert "Model trained, evaluated, and saved." in result.log

    output_dir = jobs.JOBS_DIR / job.id
    assert (output_dir / "models" / "random_forest_model.pkl").exists()
    assert (output_dir / "results" / "evaluation_metrics.txt").exists()


def test_execute_job_records_failure_without_claiming_success(session, project_and_user, monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(jobs, "PIPELINE_SCRIPTS", ["collect_data.py", "does_not_exist.py"])
    project, user = project_and_user
    job = jobs.create_job(session, project.id, user.id)
    session.commit()

    result = jobs.execute_job(session, job.id)

    assert result.status == JobStatus.FAILED
    assert result.error_message is not None
    assert "does_not_exist.py" in result.error_message


def test_execute_job_is_audited(session, project_and_user, monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    project, user = project_and_user
    job = jobs.create_job(session, project.id, user.id)
    session.commit()
    jobs.execute_job(session, job.id)

    actions = [e.action for e in audit.list_events_for_actor(session, user.id)]
    assert "job.create" in actions
    assert "job.completed" in actions
