from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ai_wasteguard import permissions, registry
from api.deps import get_current_user, get_db, require_owned_project
from api.schemas import ProjectCreateRequest, ProjectResponse

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


def _to_response(project) -> ProjectResponse:
    return ProjectResponse(
        id=project.id,
        title=project.title,
        description=project.description,
        disease_focus=project.disease_focus,
        amr_focus=project.amr_focus,
        status=project.status.value,
        created_at=project.created_at,
    )


@router.get("", response_model=list[ProjectResponse])
def list_projects(current_user=Depends(get_current_user), db: Session = Depends(get_db)) -> list[ProjectResponse]:
    projects = registry.list_projects_for_owner(db, current_user.id)
    return [_to_response(p) for p in projects]


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: ProjectCreateRequest, current_user=Depends(get_current_user), db: Session = Depends(get_db)
) -> ProjectResponse:
    if current_user.role not in permissions.CAN_CREATE_PROJECT:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{current_user.role.value}' is not permitted to create a project.",
        )
    try:
        project = registry.create_project(
            db,
            owner_id=current_user.id,
            title=payload.title,
            description=payload.description,
            disease_focus=payload.disease_focus,
            amr_focus=payload.amr_focus,
        )
    except registry.ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return _to_response(project)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)
) -> ProjectResponse:
    project = require_owned_project(db, project_id, current_user)
    return _to_response(project)
