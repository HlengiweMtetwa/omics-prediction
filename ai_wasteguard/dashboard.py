"""Dashboard summary aggregation (Part XV #72: active projects, sites,
samples, job status breakdown, approved models, recent activity).

Pure read aggregation over existing tables - no new schema. Counts are
computed with SQL COUNT rather than loading full rows, since this is meant
to stay cheap as data grows.
"""
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ai_wasteguard.models import (
    AuditLog,
    JobStatus,
    MLModel,
    ModelApprovalStatus,
    PipelineJob,
    Project,
    ProjectStatus,
    Sample,
    SamplingEvent,
    Site,
)


@dataclass
class DashboardSummary:
    active_projects: int = 0
    sites: int = 0
    samples: int = 0
    jobs_queued: int = 0
    jobs_running: int = 0
    jobs_completed: int = 0
    jobs_failed: int = 0
    approved_models: list[MLModel] = field(default_factory=list)
    recent_activity: list[AuditLog] = field(default_factory=list)


def _scalar_count(session: Session, model, *criteria) -> int:
    return session.execute(select(func.count()).select_from(model).where(*criteria)).scalar_one()


def get_dashboard_summary(session: Session, owner_id: str, recent_activity_limit: int = 10) -> DashboardSummary:
    project_ids = select(Project.id).where(Project.owner_id == owner_id).scalar_subquery()
    site_ids = select(Site.id).where(Site.project_id.in_(project_ids)).scalar_subquery()
    event_ids = select(SamplingEvent.id).where(SamplingEvent.site_id.in_(site_ids)).scalar_subquery()

    active_projects = _scalar_count(
        session, Project, Project.owner_id == owner_id, Project.status == ProjectStatus.ACTIVE
    )
    sites = _scalar_count(session, Site, Site.project_id.in_(project_ids))
    samples = _scalar_count(session, Sample, Sample.sampling_event_id.in_(event_ids))

    def _job_count(status: JobStatus) -> int:
        return _scalar_count(session, PipelineJob, PipelineJob.project_id.in_(project_ids), PipelineJob.status == status)

    approved_models = list(
        session.execute(
            select(MLModel)
            .where(MLModel.project_id.in_(project_ids), MLModel.approval_status == ModelApprovalStatus.APPROVED)
            .order_by(MLModel.approved_at.desc())
        ).scalars()
    )

    recent_activity = list(
        session.execute(
            select(AuditLog)
            .where(AuditLog.actor_user_id == owner_id)
            .order_by(AuditLog.created_at.desc())
            .limit(recent_activity_limit)
        ).scalars()
    )

    return DashboardSummary(
        active_projects=active_projects,
        sites=sites,
        samples=samples,
        jobs_queued=_job_count(JobStatus.QUEUED),
        jobs_running=_job_count(JobStatus.RUNNING),
        jobs_completed=_job_count(JobStatus.COMPLETED),
        jobs_failed=_job_count(JobStatus.FAILED),
        approved_models=approved_models,
        recent_activity=recent_activity,
    )
