"""ORM model / relationship tests for the core registry entities."""
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai_wasteguard import auth
from ai_wasteguard.db import Base
from ai_wasteguard.models import Project, Sample, SamplingEvent, Site


@pytest.fixture()
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    with Session() as s:
        yield s


def test_project_site_sampling_event_sample_chain_persists(session):
    owner = auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password")
    session.flush()

    project = Project(title="Wastewater AMR Pilot", owner_id=owner.id)
    session.add(project)
    session.flush()

    site = Site(project_id=project.id, name="Site A", country="ZA")
    session.add(site)
    session.flush()

    event = SamplingEvent(site_id=site.id, collected_at=datetime.now(timezone.utc))
    session.add(event)
    session.flush()

    sample = Sample(sampling_event_id=event.id, sample_type="composite")
    session.add(sample)
    session.commit()

    session.refresh(project)
    session.refresh(site)
    session.refresh(event)

    assert project.owner.email == "jane@example.com"
    assert project.sites[0].id == site.id
    assert site.sampling_events[0].id == event.id
    assert event.samples[0].id == sample.id


def test_duplicate_replicate_within_same_event_is_rejected(session):
    owner = auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password")
    session.flush()
    project = Project(title="Pilot", owner_id=owner.id)
    session.add(project)
    session.flush()
    site = Site(project_id=project.id, name="Site A")
    session.add(site)
    session.flush()
    event = SamplingEvent(site_id=site.id, collected_at=datetime.now(timezone.utc))
    session.add(event)
    session.flush()

    session.add(Sample(sampling_event_id=event.id, replicate=1))
    session.flush()
    session.add(Sample(sampling_event_id=event.id, replicate=1))

    with pytest.raises(Exception):
        session.flush()
