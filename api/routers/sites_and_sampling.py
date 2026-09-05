from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_wasteguard import permissions, registry
from api.deps import (
    get_current_user,
    get_db,
    require_owned_project,
    require_owned_sampling_event,
    require_owned_site,
)
from api.schemas import (
    SampleCreateRequest,
    SampleResponse,
    SamplingEventCreateRequest,
    SamplingEventResponse,
    SiteCreateRequest,
    SiteResponse,
)

router = APIRouter(prefix="/api/v1", tags=["sites-and-sampling"])


def _require_can_manage(role) -> None:
    if role not in permissions.CAN_MANAGE_SITES_AND_SAMPLING:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{role.value}' is not permitted to manage sites/sampling events/samples.",
        )


def _site_response(site) -> SiteResponse:
    return SiteResponse(
        id=site.id,
        project_id=site.project_id,
        name=site.name,
        country=site.country,
        region=site.region,
        latitude=site.latitude,
        longitude=site.longitude,
        site_type=site.site_type,
        created_at=site.created_at,
    )


def _event_response(event) -> SamplingEventResponse:
    return SamplingEventResponse(
        id=event.id,
        site_id=event.site_id,
        collected_at=event.collected_at,
        sample_matrix=event.sample_matrix,
        collector=event.collector,
        notes=event.notes,
        created_at=event.created_at,
    )


def _sample_response(sample) -> SampleResponse:
    return SampleResponse(
        id=sample.id,
        sampling_event_id=sample.sampling_event_id,
        sample_type=sample.sample_type,
        replicate=sample.replicate,
        lab_identifier=sample.lab_identifier,
        analysis_status=sample.analysis_status.value,
        created_at=sample.created_at,
    )


# --- Sites ---


@router.get("/projects/{project_id}/sites", response_model=list[SiteResponse])
def list_sites(project_id: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_owned_project(db, project_id, current_user)
    return [_site_response(s) for s in registry.list_sites_for_project(db, project_id)]


@router.post("/projects/{project_id}/sites", response_model=SiteResponse, status_code=status.HTTP_201_CREATED)
def create_site(
    project_id: str,
    payload: SiteCreateRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_owned_project(db, project_id, current_user)
    _require_can_manage(current_user.role)
    try:
        site = registry.create_site(
            db,
            project_id=project_id,
            name=payload.name,
            country=payload.country,
            region=payload.region,
            latitude=payload.latitude,
            longitude=payload.longitude,
            site_type=payload.site_type,
            actor_user_id=current_user.id,
        )
    except registry.ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return _site_response(site)


# --- Sampling events ---


@router.get("/sites/{site_id}/sampling-events", response_model=list[SamplingEventResponse])
def list_sampling_events(site_id: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_owned_site(db, site_id, current_user)
    return [_event_response(e) for e in registry.list_sampling_events_for_site(db, site_id)]


@router.post(
    "/sites/{site_id}/sampling-events",
    response_model=SamplingEventResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_sampling_event(
    site_id: str,
    payload: SamplingEventCreateRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_owned_site(db, site_id, current_user)
    _require_can_manage(current_user.role)
    try:
        event = registry.create_sampling_event(
            db,
            site_id=site_id,
            collected_at=payload.collected_at,
            sample_matrix=payload.sample_matrix,
            collector=payload.collector,
            notes=payload.notes,
            actor_user_id=current_user.id,
        )
    except registry.ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return _event_response(event)


# --- Samples ---


@router.get("/sampling-events/{event_id}/samples", response_model=list[SampleResponse])
def list_samples(event_id: str, current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    require_owned_sampling_event(db, event_id, current_user)
    return [_sample_response(s) for s in registry.list_samples_for_event(db, event_id)]


@router.post(
    "/sampling-events/{event_id}/samples", response_model=SampleResponse, status_code=status.HTTP_201_CREATED
)
def create_sample(
    event_id: str,
    payload: SampleCreateRequest,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    require_owned_sampling_event(db, event_id, current_user)
    _require_can_manage(current_user.role)
    try:
        sample = registry.create_sample(
            db,
            sampling_event_id=event_id,
            sample_type=payload.sample_type,
            replicate=payload.replicate,
            lab_identifier=payload.lab_identifier,
            actor_user_id=current_user.id,
        )
    except IntegrityError:
        # Duplicate replicate for this event (registry.Sample's
        # UniqueConstraint) - surface it as a 409, not a 500.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Replicate {payload.replicate} already exists for this sampling event.",
        )
    return _sample_response(sample)
