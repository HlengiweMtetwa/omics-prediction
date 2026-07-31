import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sqlalchemy import select

from ai_wasteguard import admin, auth
from ai_wasteguard.db import Base
from ai_wasteguard.models import AuditLog, UserRole


@pytest.fixture()
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}", future=True)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, future=True)
    with Session() as s:
        yield s


def test_promote_existing_user_to_administrator(session):
    auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password", role=UserRole.RESEARCHER)
    session.commit()

    user = admin.promote_user_to_administrator(session, "jane@example.com")
    session.commit()

    assert user.role == UserRole.ADMINISTRATOR


def test_promote_normalizes_email(session):
    auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password")
    session.commit()

    user = admin.promote_user_to_administrator(session, "  Jane@Example.com  ")

    assert user.role == UserRole.ADMINISTRATOR


def test_promote_unknown_email_raises_clear_error(session):
    with pytest.raises(admin.UserNotFound):
        admin.promote_user_to_administrator(session, "nobody@example.com")


def test_promotion_is_audited_without_misattributing_actor(session):
    user = auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password")
    session.commit()

    admin.promote_user_to_administrator(session, "jane@example.com")
    session.commit()

    promote_events = list(
        session.execute(select(AuditLog).where(AuditLog.action == "admin.promote")).scalars()
    )
    assert len(promote_events) == 1
    event = promote_events[0]
    # Recorded against the user as the resource, but the actor is None -
    # this was an out-of-band operator action, not something the user did
    # to themselves, and must not be misattributed as such.
    assert event.resource_id == user.id
    assert event.actor_user_id is None
