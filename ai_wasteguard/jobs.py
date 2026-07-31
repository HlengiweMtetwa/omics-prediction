"""Pipeline job submission and execution.

Runs the existing synthetic demo pipeline (collect_data.py ->
prepare_dataset.py -> train_model.py) as real subprocesses against an
isolated per-job directory, so a job's reported status reflects what
actually happened (non-zero exit -> FAILED, with the captured output kept
as the log) rather than being assumed to succeed.

This executes synchronously when called; the caller (the UI) is
responsible for running it off the main thread if it shouldn't block.
"""
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_wasteguard import audit
from ai_wasteguard.config import BASE_DIR
from ai_wasteguard.models import JobStatus, PipelineJob

JOBS_DIR = Path(os.environ.get("JOBS_DIR", BASE_DIR / "instance" / "jobs"))

# Order matters: each step depends on the previous step's output.
PIPELINE_SCRIPTS = ["collect_data.py", "prepare_dataset.py", "train_model.py"]
SUBPROCESS_TIMEOUT_SECONDS = 120


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

    log_parts: list[str] = []
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

    job.log = "\n\n".join(log_parts)
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
