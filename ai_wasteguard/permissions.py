"""Role-based access control policy.

A single place defining which roles may perform which registry mutations.
Pages must call require_role() before invoking a mutating registry/upload
function rather than re-implementing role checks locally.
"""
from ai_wasteguard.models import UserRole

CAN_CREATE_PROJECT = {UserRole.ADMINISTRATOR, UserRole.RESEARCHER}
CAN_MANAGE_SITES_AND_SAMPLING = {UserRole.ADMINISTRATOR, UserRole.RESEARCHER, UserRole.LABORATORY_SCIENTIST}
CAN_UPLOAD = {UserRole.ADMINISTRATOR, UserRole.RESEARCHER, UserRole.LABORATORY_SCIENTIST}
CAN_RUN_PIPELINES = {UserRole.ADMINISTRATOR, UserRole.RESEARCHER, UserRole.LABORATORY_SCIENTIST}

# Roles a user may self-select at registration. Administrator is granted
# out-of-band (e.g. direct DB/admin action), never via self-registration.
SELF_REGISTERABLE_ROLES = [
    UserRole.RESEARCHER,
    UserRole.LABORATORY_SCIENTIST,
    UserRole.PUBLIC_HEALTH_OFFICIAL,
    UserRole.STUDENT,
    UserRole.VIEWER,
]


class PermissionDenied(Exception):
    pass


def require_role(role: UserRole, allowed: set[UserRole], action: str) -> None:
    if role not in allowed:
        raise PermissionDenied(f"Role '{role.value}' is not permitted to {action}.")
