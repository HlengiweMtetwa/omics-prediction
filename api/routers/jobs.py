import threading

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ai_wasteguard import jobs as jobs_service, permissions
from ai_wasteguard.db import get_session
from ai_wasteguard.models import PipelineJob
from api.deps import get_current_user, get_db, require_owned_project
from api.schemas import JobCreateRequest, JobResponse

router = APIRouter(prefix="/api/v1", tags=["jobs"])


def _to_response(job) -> JobResponse:
    return JobResponse(
        id=job.id,
        project_id=job.project_id,
        pipeline_name=job.pipeline_name,
        status=job.status.value,
        error_message=job.error_message,
        created_at=job.created_at,
        started_at=job.started_at,
        completed_at=job.completed_at,
    )


def _run_job_in_background(job_id: str) -> None:
    with get_session() as bg_session:
        jobs_service.execute_job(bg_session, job_id)


@router.get("/projects/{project_id}/jobs", response_model=list[JobResponse])
def list_jobs(project_id: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_owned_project(db, project_id, current_user)
    return [_to_response(j) for j in jobs_service.list_jobs_for_project(db, project_id)]


@router.post(
    "/projects/{project_id}/jobs", response_model=JobResponse, status_code=status.HTTP_201_CREATED
)
def create_job(
    project_id: str,
    payload: JobCreateRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    project = require_owned_project(db, project_id, current_user)
    if current_user.role not in permissions.CAN_RUN_PIPELINES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{current_user.role.value}' is not permitted to submit pipeline jobs.",
        )
    job = jobs_service.create_job(db, project.id, current_user.id, pipeline_name=payload.pipeline_name)
    response = _to_response(job)
    # Commit explicitly before starting the background thread: it opens its
    # own session (get_session, not this request's `db`), and FastAPI only
    # commits/closes `db` at dependency teardown *after* this function
    # returns - by which point the thread would already be racing to read a
    # row that isn't durably visible yet.
    db.commit()
    threading.Thread(target=_run_job_in_background, args=(job.id,), daemon=True).start()
    return response


@router.get("/jobs/{job_id}", response_model=JobResponse)
def get_job(job_id: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    job = db.get(PipelineJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    require_owned_project(db, job.project_id, current_user)
    return _to_response(job)
