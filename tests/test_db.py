"""Regression test for a real bug caught during manual verification: pages
throughout this app follow the pattern

    with get_session() as session:
        obj = some_service_call(session, ...)
    st.success(f"... {obj.some_field} ...")

reading an ORM object's attributes *after* the session context has closed.
With SQLAlchemy's default expire_on_commit=True that raises
DetachedInstanceError. ai_wasteguard/db.py sets expire_on_commit=False
specifically so this pattern works.
"""
from sqlalchemy import create_engine

from ai_wasteguard import auth, db


def test_object_attributes_remain_readable_after_get_session_exits(tmp_path):
    """Repoints db.SessionLocal's *bind* only, via sessionmaker.configure -
    every other setting (expire_on_commit in particular) stays exactly what
    db.py configures, so this genuinely exercises that configuration rather
    than re-declaring it in the test."""
    engine = create_engine(
        f"sqlite:///{tmp_path / 'test.db'}", connect_args={"check_same_thread": False}, future=True
    )
    db.Base.metadata.create_all(engine)

    original_bind = db.SessionLocal.kw.get("bind")
    db.SessionLocal.configure(bind=engine)
    try:
        with db.get_session() as session:
            user = auth.register_user(session, "Jane Doe", "jane@example.com", "correct-password")

        # session is closed here - this must not raise DetachedInstanceError.
        assert user.email == "jane@example.com"
        assert user.full_name == "Jane Doe"
    finally:
        db.SessionLocal.configure(bind=original_bind)
