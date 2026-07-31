"""Project summary reports.

Aggregates registry, upload and job-tracking state into a single
human-readable HTML report, persisted to disk with a content hash recorded
in the database (Part VI #26 / Part XVII) - not a scientific finding, just
a snapshot of what is registered and what pipeline runs produced.
"""
import hashlib
import html
import os
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_wasteguard import audit, jobs as jobs_service, registry, uploads as uploads_service
from ai_wasteguard.config import BASE_DIR
from ai_wasteguard.models import JobStatus, Project, Report

REPORTS_DIR = Path(os.environ.get("REPORTS_DIR", BASE_DIR / "instance" / "reports"))

DISCLAIMER = (
    "This report summarizes registered surveillance metadata and pipeline run "
    "history. Where model metrics are included, they were produced against "
    "synthetic demonstration data with no true predictive signal and must not "
    "be interpreted as an environmental disease signal, a risk assessment, or "
    "a public-health finding. This is not a clinical diagnosis."
)


def _e(value) -> str:
    return html.escape(str(value)) if value is not None else ""


def _render_html(project, sites, samples_count, uploads_count, upload_names, job_list) -> str:
    site_rows = "".join(
        f"<tr><td>{_e(s.name)}</td><td>{_e(s.country or '')}</td><td>{_e(s.site_type or '')}</td></tr>"
        for s in sites
    ) or "<tr><td colspan='3'><em>No sites registered.</em></td></tr>"

    upload_list = "".join(f"<li>{_e(name)}</li>" for name in upload_names) or "<li><em>No files uploaded.</em></li>"

    job_rows = ""
    latest_metrics_html = ""
    for job in job_list:
        job_rows += (
            f"<tr><td>{_e(job.pipeline_name)}</td><td>{_e(job.status.value)}</td>"
            f"<td>{_e(job.created_at.isoformat())}</td></tr>"
        )
    if job_list:
        latest = job_list[0]
        if latest.status == JobStatus.COMPLETED and latest.output_dir:
            metrics_path = Path(latest.output_dir) / "results" / "evaluation_metrics.txt"
            if metrics_path.exists():
                latest_metrics_html = f"<pre>{_e(metrics_path.read_text())}</pre>"
    if not job_rows:
        job_rows = "<tr><td colspan='3'><em>No pipeline jobs submitted.</em></td></tr>"

    return f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Project report: {_e(project.title)}</title></head>
<body style="font-family: sans-serif; max-width: 800px; margin: 2rem auto;">
<h1>Project summary report</h1>
<h2>{_e(project.title)}</h2>
<p><strong>Disease/AMR focus:</strong> {_e(project.disease_focus or '—')} &middot;
<strong>AMR focus:</strong> {_e('yes' if project.amr_focus else 'no')} &middot;
<strong>Status:</strong> {_e(project.status.value)}</p>
<p>{_e(project.description or '')}</p>

<blockquote style="border-left: 4px solid #b45309; padding-left: 1rem; color: #92400e;">
{_e(DISCLAIMER)}
</blockquote>

<h3>Sites ({len(sites)})</h3>
<table border="1" cellpadding="4" cellspacing="0">
<tr><th>Name</th><th>Country</th><th>Type</th></tr>
{site_rows}
</table>

<h3>Samples registered: {samples_count}</h3>

<h3>Uploaded files ({uploads_count})</h3>
<ul>{upload_list}</ul>

<h3>Pipeline jobs</h3>
<table border="1" cellpadding="4" cellspacing="0">
<tr><th>Pipeline</th><th>Status</th><th>Submitted</th></tr>
{job_rows}
</table>
{f"<h4>Latest completed job - evaluation metrics</h4>{latest_metrics_html}" if latest_metrics_html else ""}
</body></html>
"""


def generate_project_summary_report(session: Session, project_id: str, generated_by: str) -> Report:
    project = session.get(Project, project_id)

    sites = registry.list_sites_for_project(session, project_id)
    samples_count = 0
    upload_names: list[str] = []
    for site in sites:
        for event in registry.list_sampling_events_for_site(session, site.id):
            for sample in registry.list_samples_for_event(session, event.id):
                samples_count += 1
                upload_names.extend(
                    f.original_filename for f in uploads_service.list_uploads_for_sample(session, sample.id)
                )

    job_list = jobs_service.list_jobs_for_project(session, project_id)

    content = _render_html(project, sites, samples_count, len(upload_names), upload_names, job_list)
    content_bytes = content.encode("utf-8")

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    file_name = f"{uuid4()}.html"
    file_path = REPORTS_DIR / file_name
    file_path.write_bytes(content_bytes)

    report = Report(
        project_id=project_id,
        report_type="project_summary",
        generated_by=generated_by,
        file_path=str(file_path),
        content_hash=hashlib.sha256(content_bytes).hexdigest(),
    )
    session.add(report)
    session.flush()
    audit.log_event(
        session, "report.create", actor_user_id=generated_by, resource_type="report", resource_id=report.id
    )
    return report


def list_reports_for_project(session: Session, project_id: str) -> list[Report]:
    return list(
        session.execute(
            select(Report).where(Report.project_id == project_id).order_by(Report.created_at.desc())
        ).scalars()
    )
