from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ai_wasteguard import model_registry, permissions
from ai_wasteguard.models import MLModel, PipelineJob
from api.deps import get_current_user, get_db, require_owned_project
from api.schemas import ModelRegisterRequest, ModelResponse

router = APIRouter(prefix="/api/v1", tags=["models"])


def _to_response(model: MLModel) -> ModelResponse:
    return ModelResponse(
        id=model.id,
        project_id=model.project_id,
        job_id=model.job_id,
        name=model.name,
        algorithm=model.algorithm,
        target_variable=model.target_variable,
        metrics=model.metrics,
        intended_use=model.intended_use,
        prohibited_use=model.prohibited_use,
        approval_status=model.approval_status.value,
        registered_by=model.registered_by,
        approved_by=model.approved_by,
        created_at=model.created_at,
        approved_at=model.approved_at,
    )


@router.get("/projects/{project_id}/models", response_model=list[ModelResponse])
def list_models(project_id: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_owned_project(db, project_id, current_user)
    return [_to_response(m) for m in model_registry.list_models_for_project(db, project_id)]


@router.post("/projects/{project_id}/models", response_model=ModelResponse, status_code=status.HTTP_201_CREATED)
def register_model(
    project_id: str,
    payload: ModelRegisterRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_owned_project(db, project_id, current_user)
    if current_user.role not in permissions.CAN_REGISTER_MODELS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{current_user.role.value}' is not permitted to register models.",
        )
    job = db.get(PipelineJob, payload.job_id)
    if job is None or job.project_id != project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found for this project.")
    try:
        model = model_registry.register_model_from_job(db, payload.job_id, current_user.id, name=payload.name)
    except model_registry.ModelRegistrationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return _to_response(model)


@router.post("/models/{model_id}/approve", response_model=ModelResponse)
def approve_model(model_id: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    model = db.get(MLModel, model_id)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Model not found.")
    require_owned_project(db, model.project_id, current_user)
    if current_user.role not in permissions.CAN_APPROVE_MODELS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{current_user.role.value}' is not permitted to approve models.",
        )
    model = model_registry.approve_model(db, model_id, current_user.id)
    return _to_response(model)
