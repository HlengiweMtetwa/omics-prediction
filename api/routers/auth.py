from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ai_wasteguard import auth, permissions
from ai_wasteguard.models import UserRole
from ai_wasteguard.tokens import create_access_token
from api.deps import get_current_user, get_db
from api.schemas import LoginRequest, RegisterRequest, TokenResponse, UserResponse

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> UserResponse:
    try:
        role = UserRole(payload.role)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid role '{payload.role}'.")
    if role not in permissions.SELF_REGISTERABLE_ROLES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Role '{role.value}' is not self-registerable.",
        )

    try:
        user = auth.register_user(
            db,
            full_name=payload.full_name,
            email=payload.email,
            password=payload.password,
            institution=payload.institution,
            role=role,
        )
    except auth.EmailAlreadyRegistered as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return UserResponse(id=user.id, full_name=user.full_name, email=user.email, role=user.role.value, institution=user.institution)


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        user = auth.authenticate_user(db, payload.email, payload.password)
    except auth.AccountLocked as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except auth.AccountDisabled as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc))
    except auth.InvalidCredentials as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserResponse)
def me(current_user=Depends(get_current_user)) -> UserResponse:
    return UserResponse(
        id=current_user.id,
        full_name=current_user.full_name,
        email=current_user.email,
        role=current_user.role.value,
        institution=current_user.institution,
    )
