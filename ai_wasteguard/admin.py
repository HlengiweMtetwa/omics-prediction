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
from ai_wasteguard.models import User, UserRole


class UserNotFound(Exception):
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
