"""Out-of-band administrator promotion.

Administrator is deliberately excluded from self-registration
(permissions.SELF_REGISTERABLE_ROLES). This module is the one supported way
to grant it: promote an already-registered user, run by someone with
direct access to the deployment (CLI/operator action), never through the
web UI.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_wasteguard import audit
from ai_wasteguard.auth import normalize_email
from ai_wasteguard.models import AccountStatus, User, UserRole


class UserNotFound(Exception):
    pass


class RoleChangeError(Exception):
    pass


def promote_user_to_administrator(session: Session, email: str) -> User:
    normalized_email = normalize_email(email)
    user = session.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
    if user is None:
        raise UserNotFound(f"No registered account for {normalized_email}. They must register first.")

    previous_role = user.role
    user.role = UserRole.ADMINISTRATOR
    session.flush()
    # actor_user_id is deliberately None: this is an out-of-band operator
    # action (CLI, run outside any authenticated web session), not something
    # the promoted user did themselves - recording it as their own action
    # would misattribute it.
    audit.log_event(
        session,
        "admin.promote",
        actor_user_id=None,
        resource_type="user",
        resource_id=user.id,
        details=f"{normalized_email} promoted from {previous_role.value} to administrator (out-of-band)",
    )
    return user


def list_all_users(session: Session) -> list[User]:
    return list(session.execute(select(User).order_by(User.created_at)).scalars())


def _require_non_administrator_target(user: User) -> None:
    # Generalizes the same rule as promote_user_to_administrator: an
    # Administrator account's role or status is never changed through the
    # web-facing action layer, only out-of-band (CLI/direct DB access).
    # Since callers of the functions below are themselves required to be
    # Administrators, this also prevents an admin from acting on their own
    # account through this path - a useful side effect, not a separate check.
    if user.role == UserRole.ADMINISTRATOR:
        raise RoleChangeError(
            "This account is an Administrator; its role or status cannot be changed through this action."
        )


def change_user_role(session: Session, user_id: str, new_role_value: str, actor_user_id: str) -> User:
    if new_role_value == UserRole.ADMINISTRATOR.value:
        raise RoleChangeError(
            "Administrator cannot be granted through this action - use scripts/create_admin.py."
        )
    try:
        new_role = UserRole(new_role_value)
    except ValueError:
        raise RoleChangeError(f"Unknown role '{new_role_value}'.")

    user = session.get(User, user_id)
    if user is None:
        raise UserNotFound("User not found.")
    _require_non_administrator_target(user)

    previous_role = user.role
    user.role = new_role
    session.flush()
    audit.log_event(
        session,
        "user.role_change",
        actor_user_id=actor_user_id,
        resource_type="user",
        resource_id=user.id,
        details=f"{previous_role.value} -> {new_role.value}",
    )
    return user


def set_account_status(session: Session, user_id: str, new_status: AccountStatus, actor_user_id: str) -> User:
    user = session.get(User, user_id)
    if user is None:
        raise UserNotFound("User not found.")
    _require_non_administrator_target(user)

    user.status = new_status
    session.flush()
    action = "user.enable" if new_status == AccountStatus.ACTIVE else "user.disable"
    audit.log_event(session, action, actor_user_id=actor_user_id, resource_type="user", resource_id=user.id)
    return user
