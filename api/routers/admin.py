from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ai_wasteguard import admin as admin_service, permissions
from ai_wasteguard.models import AccountStatus, User
from api.deps import get_current_user, get_db
from api.schemas import AdminUserResponse, RoleChangeRequest

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


def _require_admin(current_user: User) -> None:
    if current_user.role not in permissions.CAN_MANAGE_USERS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{current_user.role.value}' is not permitted to manage users.",
        )


def _to_response(user: User) -> AdminUserResponse:
    return AdminUserResponse(
        id=user.id,
        full_name=user.full_name,
        email=user.email,
        institution=user.institution,
        role=user.role.value,
        status=user.status.value,
        created_at=user.created_at,
        last_login_at=user.last_login_at,
    )


@router.get("/users", response_model=list[AdminUserResponse])
def list_users(current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(current_user)
    return [_to_response(u) for u in admin_service.list_all_users(db)]


@router.post("/users/{user_id}/role", response_model=AdminUserResponse)
def change_role(
    user_id: str,
    payload: RoleChangeRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    _require_admin(current_user)
    try:
        user = admin_service.change_user_role(db, user_id, payload.role, current_user.id)
    except admin_service.UserNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except admin_service.RoleChangeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return _to_response(user)


@router.post("/users/{user_id}/disable", response_model=AdminUserResponse)
def disable_user(user_id: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(current_user)
    try:
        user = admin_service.set_account_status(db, user_id, AccountStatus.DISABLED, current_user.id)
    except admin_service.UserNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except admin_service.RoleChangeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return _to_response(user)


@router.post("/users/{user_id}/enable", response_model=AdminUserResponse)
def enable_user(user_id: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    _require_admin(current_user)
    try:
        user = admin_service.set_account_status(db, user_id, AccountStatus.ACTIVE, current_user.id)
    except admin_service.UserNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except admin_service.RoleChangeError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return _to_response(user)
