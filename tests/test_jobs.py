import io
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai_wasteguard import audit, auth, jobs, registry, uploads as uploads_service
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


def _upload_csv_to_project(session, project_id, user_id, content: bytes, filename="data.csv"):
    site = registry.create_site(session, project_id, "Site A", actor_user_id=user_id)
    session.flush()
    event = registry.create_sampling_event(
        session, site.id, datetime(2026, 1, 1, tzinfo=timezone.utc), actor_user_id=user_id
    )
    session.flush()
    sample = registry.create_sample(session, event.id, actor_user_id=user_id)
    session.flush()
    upload = uploads_service.save_upload(session, sample.id, user_id, filename, io.BytesIO(content))
    session.commit()
    return upload


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


def test_execute_job_with_no_upload_falls_back_to_labeled_synthetic_demo(session, project_and_user, monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    project, user = project_and_user
    job = jobs.create_job(session, project.id, user.id)
    session.commit()

    result = jobs.execute_job(session, job.id)

    assert result.status == JobStatus.COMPLETED
    assert "SYNTHETIC DEMO DATA" in result.log
    metrics_text = (jobs.JOBS_DIR / job.id / "results" / "evaluation_metrics.txt").read_text()
    assert "SYNTHETIC DEMO DATA" in metrics_text


def test_execute_job_with_labeled_upload_trains_a_real_model(session, project_and_user, monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(uploads_service, "UPLOAD_DIR", tmp_path / "uploads")
    project, user = project_and_user

    rows = ["feature_a,feature_b,disease_present"]
    for i in range(20):
        rows.append(f"{i},{i * 2},{i % 2}")
    _upload_csv_to_project(
        session, project.id, user.id, "\n".join(rows).encode(), filename="tb_wastewater_survey.csv"
    )

    job = jobs.create_job(session, project.id, user.id)
    session.commit()
    result = jobs.execute_job(session, job.id)

    assert result.status == JobStatus.COMPLETED, result.error_message
    assert "REAL DATA ANALYSIS" in result.log
    assert "SYNTHETIC" not in result.log
    assert "Trained RandomForestClassifier" in result.log
    assert "Accuracy:" in result.log
    # The report must show the user's own filename, not the server-generated
    # storage key it's actually stored under on disk.
    assert "Source file: tb_wastewater_survey.csv" in result.log

    output_dir = jobs.JOBS_DIR / job.id
    assert (output_dir / "models" / "random_forest_model.pkl").exists()


def test_execute_job_with_unlabeled_upload_profiles_only_no_fabricated_metrics(
    session, project_and_user, monkeypatch, tmp_path
):
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(uploads_service, "UPLOAD_DIR", tmp_path / "uploads")
    project, user = project_and_user

    rows = ["gene_a,gene_b", "1,2", "3,4", "5,6"]
    _upload_csv_to_project(session, project.id, user.id, "\n".join(rows).encode())

    job = jobs.create_job(session, project.id, user.id)
    session.commit()
    result = jobs.execute_job(session, job.id)

    assert result.status == JobStatus.COMPLETED
    assert "REAL DATA ANALYSIS" in result.log
    assert "No recognized label column found" in result.log
    assert "Accuracy:" not in result.log

    output_dir = jobs.JOBS_DIR / job.id
    assert not (output_dir / "models" / "random_forest_model.pkl").exists()


def test_execute_job_with_unreadable_upload_fails_honestly(session, project_and_user, monkeypatch, tmp_path):
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(uploads_service, "UPLOAD_DIR", tmp_path / "uploads")
    project, user = project_and_user

    # A .json upload whose content isn't valid JSON - save_upload only checks
    # the extension, so this reaches analyze_upload and must fail there.
    _upload_csv_to_project(session, project.id, user.id, b"not actually json{{{", filename="broken.json")

    job = jobs.create_job(session, project.id, user.id)
    session.commit()
    result = jobs.execute_job(session, job.id)

    assert result.status == JobStatus.FAILED
    assert result.error_message is not None
