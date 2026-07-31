"""Model registry: turning a completed PipelineJob's artefact into a
tracked MLModel record with metadata, intended/prohibited use, and an
approval workflow.
"""
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_wasteguard import audit
from ai_wasteguard.models import JobStatus, MLModel, ModelApprovalStatus, PipelineJob

STANDARD_INTENDED_USE = (
    "Demonstration of an end-to-end wastewater omics machine-learning pipeline "
    "on synthetic data, for methodology and platform development purposes only."
)
STANDARD_PROHIBITED_USE = (
    "Must not be used for real surveillance, clinical diagnosis, or "
    "public-health decision-making. Trained on randomly generated synthetic "
    "data with no true predictive relationship between features and label; "
    "reported metrics do not reflect real-world performance."
)


class ModelRegistrationError(Exception):
    pass


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def register_model_from_job(
    session: Session, job_id: str, registered_by: str, name: str | None = None
) -> MLModel:
    job = session.get(PipelineJob, job_id)
    if job is None:
        raise ModelRegistrationError("Job not found.")
    if job.status != JobStatus.COMPLETED:
        raise ModelRegistrationError(f"Job status is '{job.status.value}', not 'completed' - cannot register a model.")
    if not job.output_dir:
        raise ModelRegistrationError("Job has no output directory recorded.")

    artifact_path = Path(job.output_dir) / "models" / "random_forest_model.pkl"
    if not artifact_path.exists():
        raise ModelRegistrationError("No trained model artifact found for this job.")

    metrics_path = Path(job.output_dir) / "results" / "evaluation_metrics.txt"
    metrics_text = metrics_path.read_text() if metrics_path.exists() else None

    model = MLModel(
        project_id=job.project_id,
        job_id=job.id,
        name=name or f"{job.pipeline_name}-{job.id[:8]}",
        algorithm="RandomForestClassifier",
        target_variable="disease_present",
        metrics=metrics_text,
        artifact_path=str(artifact_path),
        intended_use=STANDARD_INTENDED_USE,
        prohibited_use=STANDARD_PROHIBITED_USE,
        approval_status=ModelApprovalStatus.DRAFT,
        registered_by=registered_by,
    )
    session.add(model)
    session.flush()
    audit.log_event(
        session, "model.register", actor_user_id=registered_by, resource_type="ml_model", resource_id=model.id
    )
    return model


def approve_model(session: Session, model_id: str, approved_by: str) -> MLModel:
    model = session.get(MLModel, model_id)
    if model is None:
        raise ModelRegistrationError("Model not found.")
    model.approval_status = ModelApprovalStatus.APPROVED
    model.approved_by = approved_by
    model.approved_at = _utcnow()
    session.flush()
    audit.log_event(
        session, "model.approve", actor_user_id=approved_by, resource_type="ml_model", resource_id=model.id
    )
    return model


def list_models_for_project(session: Session, project_id: str) -> list[MLModel]:
    return list(
        session.execute(
            select(MLModel).where(MLModel.project_id == project_id).order_by(MLModel.created_at.desc())
        ).scalars()
    )
