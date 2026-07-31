"""Authentication tests.

Covers the behaviours the auth module is required to guarantee: accounts
persist across process restarts, duplicate registration is blocked, email
casing is normalized, wrong passwords fail safely, disabled/locked accounts
cannot log in, and enumeration is not possible via error messages.
"""
import os

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ai_wasteguard import auth
from ai_wasteguard.db import Base
from ai_wasteguard.models import AccountStatus, User


@pytest.fixture()
def db_path(tmp_path):
    return tmp_path / "test.db"


def _session_factory(db_path):
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, future=True)


def test_register_and_login(db_path):
    Session = _session_factory(db_path)
    with Session() as session:
        auth.register_user(session, "Jane Doe", "Jane@Example.com", "correct horse battery staple")
        session.commit()

    with Session() as session:
        user = auth.authenticate_user(session, "jane@example.com", "correct horse battery staple")
        session.commit()
        assert user.email == "jane@example.com"


def test_email_normalized_on_registration_and_duplicate_blocked(db_path):
    Session = _session_factory(db_path)
    with Session() as session:
        auth.register_user(session, "Jane Doe", "  Jane@Example.com  ", "password12345")
        session.commit()

    with Session() as session:
        with pytest.raises(auth.EmailAlreadyRegistered):
            auth.register_user(session, "Jane Doe Two", "jane@example.com", "different-password")


def test_wrong_password_fails_safely(db_path):
    Session = _session_factory(db_path)
    with Session() as session:
        auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password")
        session.commit()

    with Session() as session:
        with pytest.raises(auth.InvalidCredentials):
            auth.authenticate_user(session, "jane@example.com", "wrong-password")


def test_unknown_and_wrong_password_raise_identical_error_type(db_path):
    """Prevents user enumeration: both cases must be indistinguishable."""
    Session = _session_factory(db_path)
    with Session() as session:
        auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password")
        session.commit()

    with Session() as session:
        with pytest.raises(auth.InvalidCredentials) as unknown_exc:
            auth.authenticate_user(session, "nobody@example.com", "whatever")

    with Session() as session:
        with pytest.raises(auth.InvalidCredentials) as wrong_pw_exc:
            auth.authenticate_user(session, "jane@example.com", "wrong-password")

    assert str(unknown_exc.value) == str(wrong_pw_exc.value)


def test_account_persists_after_restart(db_path):
    """Simulates an app restart by creating a brand new engine/session
    against the same on-disk database file."""
    Session1 = _session_factory(db_path)
    with Session1() as session:
        auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password")
        session.commit()

    # Fresh engine/session pointed at the same file - simulates restart.
    engine2 = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False}, future=True)
    Session2 = sessionmaker(bind=engine2, future=True)
    with Session2() as session:
        user = auth.authenticate_user(session, "jane@example.com", "correct-password")
        assert user is not None


def test_disabled_account_cannot_log_in(db_path):
    Session = _session_factory(db_path)
    with Session() as session:
        user = auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password")
        user.status = AccountStatus.DISABLED
        session.commit()

    with Session() as session:
        with pytest.raises(auth.AccountDisabled):
            auth.authenticate_user(session, "jane@example.com", "correct-password")


def test_account_locks_after_repeated_failures(db_path, monkeypatch):
    monkeypatch.setattr(auth, "ACCOUNT_LOCKOUT_THRESHOLD", 3)
    Session = _session_factory(db_path)
    with Session() as session:
        auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password")
        session.commit()

    with Session() as session:
        for _ in range(3):
            with pytest.raises(auth.InvalidCredentials):
                auth.authenticate_user(session, "jane@example.com", "wrong-password")
        session.commit()

    with Session() as session:
        with pytest.raises(auth.AccountLocked):
            auth.authenticate_user(session, "jane@example.com", "correct-password")


def test_password_is_hashed_not_stored_in_plaintext(db_path):
    Session = _session_factory(db_path)
    with Session() as session:
        user = auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password")
        assert user.password_hash != "correct-password"
        assert user.password_hash.startswith("$argon2")
