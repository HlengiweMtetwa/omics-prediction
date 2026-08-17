"""Pipeline job submission and execution.

Prefers real analysis: if the project has an uploaded tabular data file
(csv/tsv/txt/json/xlsx/parquet), the job analyzes that actual file via
ai_wasteguard.analysis - real column statistics always, a real trained
classifier when a recognizable label column exists. Falls back to the
synthetic demo pipeline (collect_data.py -> prepare_dataset.py ->
train_model.py, all real subprocesses generating random data) only when no
such file exists, and clearly banners that fallback's output as synthetic
so it is never mistaken for a real result.

Either path reports a job's status honestly - a non-zero exit or a raised
AnalysisError becomes FAILED, never assumed success.
"""
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_wasteguard import analysis, audit, registry
from ai_wasteguard import uploads as uploads_service
from ai_wasteguard.config import BASE_DIR
from ai_wasteguard.models import PipelineJob, UploadedFile, JobStatus

JOBS_DIR = Path(os.environ.get("JOBS_DIR", BASE_DIR / "instance" / "jobs"))

# Order matters: each step depends on the previous step's output.
PIPELINE_SCRIPTS = ["collect_data.py", "prepare_dataset.py", "train_model.py"]
SUBPROCESS_TIMEOUT_SECONDS = 120

SYNTHETIC_DATA_BANNER = (
    "SYNTHETIC DEMO DATA - no analyzable file has been uploaded to this project. "
    "The figures below come from a randomly generated demonstration dataset and "
    "are not a real analysis of anything registered in this project. Upload a "
    "tabular file (csv/tsv/txt/json/xlsx/parquet) to a sample to get a real result."
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def create_job(
    session: Session, project_id: str, submitted_by: str, pipeline_name: str = "synthetic_omics_demo"
) -> PipelineJob:
    job = PipelineJob(
        project_id=project_id,
        submitted_by=submitted_by,
        pipeline_name=pipeline_name,
        status=JobStatus.QUEUED,
    )
    session.add(job)
    session.flush()
    audit.log_event(
        session, "job.create", actor_user_id=submitted_by, resource_type="pipeline_job", resource_id=job.id
    )
    return job


def list_jobs_for_project(session: Session, project_id: str) -> list[PipelineJob]:
    return list(
        session.execute(
            select(PipelineJob).where(PipelineJob.project_id == project_id).order_by(PipelineJob.created_at.desc())
        ).scalars()
    )


def _find_latest_tabular_upload(session: Session, project_id: str) -> UploadedFile | None:
    latest: UploadedFile | None = None
    for site in registry.list_sites_for_project(session, project_id):
        for event in registry.list_sampling_events_for_site(session, site.id):
            for sample in registry.list_samples_for_event(session, event.id):
                for upload in uploads_service.list_uploads_for_sample(session, sample.id):
                    if upload.file_type == "tabular" and (latest is None or upload.created_at > latest.created_at):
                        latest = upload
    return latest


def _run_real_data_job(job_dir: Path, upload: UploadedFile) -> tuple[str, str | None]:
    """Returns (log_text, error_message). error_message is None on success."""
    upload_path = uploads_service.UPLOAD_DIR / upload.storage_key
    try:
        report = analysis.analyze_upload(upload_path, job_dir / "models", display_name=upload.original_filename)
    except analysis.AnalysisError as exc:
        return f"$ analyze '{upload.original_filename}'\nFAILED: {exc}", str(exc)

    (job_dir / "results" / "evaluation_metrics.txt").write_text(report)
    return f"$ analyze '{upload.original_filename}'\n{report}", None


def _run_synthetic_demo_job(job_dir: Path) -> tuple[str, str | None]:
    """Returns (log_text, error_message). error_message is None on success."""
    log_parts: list[str] = [SYNTHETIC_DATA_BANNER]
    failure: str | None = None

    for script in PIPELINE_SCRIPTS:
        script_path = BASE_DIR / script
        try:
            result = subprocess.run(
                [sys.executable, str(script_path)],
                cwd=job_dir,
                capture_output=True,
                text=True,
                timeout=SUBPROCESS_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            log_parts.append(f"$ python {script}\n(timed out after {SUBPROCESS_TIMEOUT_SECONDS}s)")
            failure = f"'{script}' timed out."
            break

        log_parts.append(f"$ python {script}\n{result.stdout}{result.stderr}".rstrip())
        if result.returncode != 0:
            failure = f"'{script}' exited with status {result.returncode}."
            break

    metrics_path = job_dir / "results" / "evaluation_metrics.txt"
    if metrics_path.exists():
        metrics_path.write_text(f"{SYNTHETIC_DATA_BANNER}\n\n{metrics_path.read_text()}")

    return "\n\n".join(log_parts), failure


def execute_job(session: Session, job_id: str) -> PipelineJob:
    """Runs the pipeline for the given job, updating its status/log as it
    goes. Safe to call from a background thread with its own session -
    commits progress so other sessions observe status changes as they
    happen, not only at the end."""
    job = session.get(PipelineJob, job_id)
    job.status = JobStatus.RUNNING
    job.started_at = _utcnow()
    session.commit()

    job_dir = JOBS_DIR / job.id
    for subdir in ("data", "models", "results"):
        (job_dir / subdir).mkdir(parents=True, exist_ok=True)

    upload = _find_latest_tabular_upload(session, job.project_id)
    try:
        if upload is not None:
            log, failure = _run_real_data_job(job_dir, upload)
        else:
            log, failure = _run_synthetic_demo_job(job_dir)
    except Exception as exc:
        # Never let an unexpected exception leave the job stuck at RUNNING
        # forever - report it as a real failure instead.
        log, failure = f"Job failed with an unexpected error: {exc}", str(exc)

    job.log = log
    job.output_dir = str(job_dir)
    job.completed_at = _utcnow()
    job.status = JobStatus.FAILED if failure else JobStatus.COMPLETED
    job.error_message = failure
    session.commit()

    audit.log_event(
        session,
        f"job.{job.status.value}",
        actor_user_id=job.submitted_by,
        resource_type="pipeline_job",
        resource_id=job.id,
        details=failure,
    )
    return job
