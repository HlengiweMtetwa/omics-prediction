from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai_wasteguard import auth, registry
from ai_wasteguard.db import Base


@pytest.fixture()
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    with Session() as s:
        yield s


@pytest.fixture()
def owner(session):
    user = auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password")
    session.flush()
    return user


def test_create_and_list_projects_scoped_to_owner(session, owner):
    other = auth.register_user(session, "Other User", "other@example.com", "correct-password")
    session.flush()

    registry.create_project(session, owner.id, "Pilot A")
    registry.create_project(session, owner.id, "Pilot B")
    registry.create_project(session, other.id, "Someone Else's Project")
    session.commit()

    owner_projects = registry.list_projects_for_owner(session, owner.id)
    assert {p.title for p in owner_projects} == {"Pilot A", "Pilot B"}


def test_create_project_requires_title(session, owner):
    with pytest.raises(registry.ValidationError):
        registry.create_project(session, owner.id, "   ")


def test_full_registry_chain(session, owner):
    project = registry.create_project(session, owner.id, "Wastewater AMR Pilot")
    session.flush()

    site = registry.create_site(session, project.id, "Site A", country="ZA")
    session.flush()
    assert registry.list_sites_for_project(session, project.id) == [site]

    event = registry.create_sampling_event(session, site.id, datetime.now(timezone.utc), sample_matrix="influent")
    session.flush()
    assert registry.list_sampling_events_for_site(session, site.id) == [event]

    sample = registry.create_sample(session, event.id, sample_type="composite", replicate=1)
    session.commit()
    assert registry.list_samples_for_event(session, event.id) == [sample]


def test_create_sampling_event_requires_collected_at(session, owner):
    project = registry.create_project(session, owner.id, "Pilot")
    session.flush()
    site = registry.create_site(session, project.id, "Site A")
    session.flush()

    with pytest.raises(registry.ValidationError):
        registry.create_sampling_event(session, site.id, None)
