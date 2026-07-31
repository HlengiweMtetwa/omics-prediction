import hashlib
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai_wasteguard import auth, jobs, registry, reports
from ai_wasteguard.db import Base


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
    project = registry.create_project(session, user.id, "Wastewater AMR Pilot", description="Pilot description")
    session.commit()
    return project, user


def test_report_file_matches_recorded_hash(session, project_and_user, tmp_path, monkeypatch):
    monkeypatch.setattr(reports, "REPORTS_DIR", tmp_path / "reports")
    project, user = project_and_user

    report = reports.generate_project_summary_report(session, project.id, user.id)
    session.commit()

    content = open(report.file_path, "rb").read()
    assert hashlib.sha256(content).hexdigest() == report.content_hash


def test_report_includes_disclaimer_and_project_title(session, project_and_user, tmp_path, monkeypatch):
    monkeypatch.setattr(reports, "REPORTS_DIR", tmp_path / "reports")
    project, user = project_and_user

    report = reports.generate_project_summary_report(session, project.id, user.id)
    content = open(report.file_path, encoding="utf-8").read()

    assert "not a clinical diagnosis" in content
    assert "Wastewater AMR Pilot" in content


def test_report_reflects_full_registry_and_job_state(session, project_and_user, tmp_path, monkeypatch):
    monkeypatch.setattr(reports, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(jobs, "JOBS_DIR", tmp_path / "jobs")
    project, user = project_and_user

    site = registry.create_site(session, project.id, "Site A")
    session.flush()
    event = registry.create_sampling_event(session, site.id, datetime.now(timezone.utc))
    session.flush()
    registry.create_sample(session, event.id)
    job = jobs.create_job(session, project.id, user.id)
    session.commit()
    jobs.execute_job(session, job.id)

    report = reports.generate_project_summary_report(session, project.id, user.id)
    content = open(report.file_path, encoding="utf-8").read()

    assert "Site A" in content
    assert "Samples registered: 1" in content
    assert "completed" in content
    assert "Accuracy" in content  # evaluation metrics pulled from the completed job


def test_report_html_escapes_untrusted_text_fields(session, project_and_user, tmp_path, monkeypatch):
    """A project title/description containing HTML must not be injected
    unescaped into the generated report."""
    monkeypatch.setattr(reports, "REPORTS_DIR", tmp_path / "reports")
    _, user = project_and_user
    malicious_project = registry.create_project(
        session, user.id, "<script>alert(1)</script>", description="<img src=x onerror=alert(1)>"
    )
    session.commit()

    report = reports.generate_project_summary_report(session, malicious_project.id, user.id)
    content = open(report.file_path, encoding="utf-8").read()

    assert "<script>alert(1)</script>" not in content
    assert "&lt;script&gt;" in content


def test_list_reports_for_project(session, project_and_user, tmp_path, monkeypatch):
    monkeypatch.setattr(reports, "REPORTS_DIR", tmp_path / "reports")
    project, user = project_and_user

    reports.generate_project_summary_report(session, project.id, user.id)
    reports.generate_project_summary_report(session, project.id, user.id)
    session.commit()

    assert len(reports.list_reports_for_project(session, project.id)) == 2
