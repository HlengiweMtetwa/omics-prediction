import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai_wasteguard import audit, auth, permissions, registry
from ai_wasteguard.db import Base
from ai_wasteguard.models import User, UserRole


@pytest.fixture()
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    with Session() as s:
        yield s


def test_registration_and_login_are_audited(session):
    auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password")
    session.commit()
    with pytest.raises(auth.InvalidCredentials):
        auth.authenticate_user(session, "jane@example.com", "wrong-password")
    session.commit()
    auth.authenticate_user(session, "jane@example.com", "correct-password")
    session.commit()

    user = session.query(User).first()
    events = [e.action for e in audit.list_events_for_actor(session, user.id)]
    assert "register.success" in events
    assert "login.wrong_password" in events
    assert "login.success" in events


def test_registry_mutations_are_audited(session):
    owner = auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password")
    session.flush()
    project = registry.create_project(session, owner.id, "Pilot")
    session.flush()
    site = registry.create_site(session, project.id, "Site A", actor_user_id=owner.id)
    session.commit()

    events = [e.action for e in audit.list_events_for_actor(session, owner.id)]
    assert "project.create" in events
    assert "site.create" in events


def test_require_role_allows_permitted_role():
    permissions.require_role(UserRole.RESEARCHER, permissions.CAN_CREATE_PROJECT, "create a project")


def test_require_role_blocks_unpermitted_role():
    with pytest.raises(permissions.PermissionDenied):
        permissions.require_role(UserRole.VIEWER, permissions.CAN_CREATE_PROJECT, "create a project")


def test_administrator_is_always_permitted_where_others_are_restricted():
    assert UserRole.ADMINISTRATOR in permissions.CAN_CREATE_PROJECT
    assert UserRole.ADMINISTRATOR in permissions.CAN_MANAGE_SITES_AND_SAMPLING
    assert UserRole.ADMINISTRATOR in permissions.CAN_UPLOAD


def test_self_registerable_roles_exclude_administrator():
    assert UserRole.ADMINISTRATOR not in permissions.SELF_REGISTERABLE_ROLES
