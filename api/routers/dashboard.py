from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ai_wasteguard import dashboard as dashboard_service
from api.deps import get_current_user, get_db
from api.schemas import ActivityEvent, ApprovedModelSummary, DashboardResponse

router = APIRouter(prefix="/api/v1", tags=["dashboard"])


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(current_user=Depends(get_current_user), db: Session = Depends(get_db)) -> DashboardResponse:
    summary = dashboard_service.get_dashboard_summary(db, current_user.id)
    return DashboardResponse(
        active_projects=summary.active_projects,
        sites=summary.sites,
        samples=summary.samples,
        jobs_queued=summary.jobs_queued,
        jobs_running=summary.jobs_running,
        jobs_completed=summary.jobs_completed,
        jobs_failed=summary.jobs_failed,
        approved_models=[
            ApprovedModelSummary(id=m.id, name=m.name, algorithm=m.algorithm) for m in summary.approved_models
        ],
        recent_activity=[
            ActivityEvent(
                action=e.action, resource_type=e.resource_type, details=e.details, created_at=e.created_at
            )
            for e in summary.recent_activity
        ],
    )
