"""Shared Streamlit session/auth glue for the multipage registry app.

Deliberately thin: all real logic lives in ai_wasteguard (auth, registry) so
it stays testable without a Streamlit runtime. This module only bridges
that logic to st.session_state.
"""
import streamlit as st
from sqlalchemy import select
from sqlalchemy.exc import OperationalError

from ai_wasteguard import auth
from ai_wasteguard.db import get_session
from ai_wasteguard.models import User


def db_is_ready() -> bool:
    """False if migrations haven't been applied yet."""
    try:
        with get_session() as session:
            session.execute(select(User).limit(1))
        return True
    except OperationalError:
        return False


def current_user_id() -> str | None:
    return st.session_state.get("user_id")


def is_logged_in() -> bool:
    return current_user_id() is not None


def login(email: str, password: str) -> None:
    """Raises ai_wasteguard.auth.AuthError subclasses on failure."""
    with get_session() as session:
        user = auth.authenticate_user(session, email, password)
        st.session_state["user_id"] = user.id
        st.session_state["user_email"] = user.email
        st.session_state["user_full_name"] = user.full_name
        st.session_state["user_role"] = user.role.value


def register(full_name: str, email: str, password: str, institution: str | None) -> None:
    """Raises ai_wasteguard.auth.AuthError subclasses on failure."""
    with get_session() as session:
        auth.register_user(session, full_name, email, password, institution=institution)


def logout() -> None:
    for key in ("user_id", "user_email", "user_full_name", "user_role"):
        st.session_state.pop(key, None)


def require_login() -> str:
    """Returns the current user id, or stops page execution with a
    message if no one is logged in."""
    user_id = current_user_id()
    if not user_id:
        st.warning("Please log in on the Home page to access this page.")
        st.stop()
    return user_id
