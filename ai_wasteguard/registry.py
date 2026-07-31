"""Project / site / sampling-event / sample registry service.

Presentation layers (Streamlit today, a future API) call these functions
rather than querying the ORM directly, per the platform's layering rules.
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_wasteguard.models import Project, Sample, SamplingEvent, Site


class ValidationError(Exception):
    pass


def _require_text(value: str, field_name: str) -> str:
    value = (value or "").strip()
    if not value:
        raise ValidationError(f"{field_name} is required.")
    return value


def list_projects_for_owner(session: Session, owner_id: str) -> list[Project]:
    return list(
        session.execute(
            select(Project).where(Project.owner_id == owner_id).order_by(Project.created_at.desc())
        ).scalars()
    )


def create_project(
    session: Session,
    owner_id: str,
    title: str,
    description: str | None = None,
    disease_focus: str | None = None,
    amr_focus: bool = False,
) -> Project:
    project = Project(
        title=_require_text(title, "Project title"),
        owner_id=owner_id,
        description=description or None,
        disease_focus=disease_focus or None,
        amr_focus=amr_focus,
    )
    session.add(project)
    session.flush()
    return project


def list_sites_for_project(session: Session, project_id: str) -> list[Site]:
    return list(
        session.execute(
            select(Site).where(Site.project_id == project_id).order_by(Site.created_at.desc())
        ).scalars()
    )


def create_site(
    session: Session,
    project_id: str,
    name: str,
    country: str | None = None,
    region: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    site_type: str | None = None,
) -> Site:
    site = Site(
        project_id=project_id,
        name=_require_text(name, "Site name"),
        country=country or None,
        region=region or None,
        latitude=latitude,
        longitude=longitude,
        site_type=site_type or None,
    )
    session.add(site)
    session.flush()
    return site


def list_sampling_events_for_site(session: Session, site_id: str) -> list[SamplingEvent]:
    return list(
        session.execute(
            select(SamplingEvent)
            .where(SamplingEvent.site_id == site_id)
            .order_by(SamplingEvent.collected_at.desc())
        ).scalars()
    )


def create_sampling_event(
    session: Session,
    site_id: str,
    collected_at: datetime,
    sample_matrix: str | None = None,
    collector: str | None = None,
    notes: str | None = None,
) -> SamplingEvent:
    if collected_at is None:
        raise ValidationError("Collection date/time is required.")
    event = SamplingEvent(
        site_id=site_id,
        collected_at=collected_at,
        sample_matrix=sample_matrix or None,
        collector=collector or None,
        notes=notes or None,
    )
    session.add(event)
    session.flush()
    return event


def list_samples_for_event(session: Session, sampling_event_id: str) -> list[Sample]:
    return list(
        session.execute(
            select(Sample)
            .where(Sample.sampling_event_id == sampling_event_id)
            .order_by(Sample.replicate)
        ).scalars()
    )


def create_sample(
    session: Session,
    sampling_event_id: str,
    sample_type: str | None = None,
    replicate: int = 1,
    lab_identifier: str | None = None,
) -> Sample:
    sample = Sample(
        sampling_event_id=sampling_event_id,
        sample_type=sample_type or None,
        replicate=replicate,
        lab_identifier=lab_identifier or None,
    )
    session.add(sample)
    session.flush()
    return sample
