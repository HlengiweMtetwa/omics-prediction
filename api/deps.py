"""FastAPI dependencies: DB session per request, and bearer-token auth.

Deliberately does not reuse Streamlit's app_state.py session-state
mechanism - the API is a second, independent presentation layer per the
platform's layering rules, authenticated statelessly via JWT rather than
a server-side session.
"""
from typing import Generator

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from ai_wasteguard.db import SessionLocal
from ai_wasteguard.models import AccountStatus, Project, Sample, SamplingEvent, Site, User
from ai_wasteguard.tokens import InvalidToken, decode_access_token

_bearer_scheme = HTTPBearer(auto_error=False)


def get_db() -> Generator[Session, None, None]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        user_id = decode_access_token(credentials.credentials)
    except InvalidToken:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists")
    if user.status != AccountStatus.ACTIVE:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    return user


# Ownership-check helpers shared by the sites/sampling-events/samples
# routers. Each returns 404 (never 403) when the resource exists but isn't
# owned by the caller - same principle as projects.get_project: don't
# confirm a resource id exists to someone who can't see it.


def require_owned_project(db: Session, project_id: str, user: User) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.owner_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found.")
    return project


def require_owned_site(db: Session, site_id: str, user: User) -> Site:
    site = db.get(Site, site_id)
    if site is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Site not found.")
    require_owned_project(db, site.project_id, user)
    return site


def require_owned_sampling_event(db: Session, event_id: str, user: User) -> SamplingEvent:
    event = db.get(SamplingEvent, event_id)
    if event is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sampling event not found.")
    require_owned_site(db, event.site_id, user)
    return event


def require_owned_sample(db: Session, sample_id: str, user: User) -> Sample:
    sample = db.get(Sample, sample_id)
    if sample is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Sample not found.")
    require_owned_sampling_event(db, sample.sampling_event_id, user)
    return sample
