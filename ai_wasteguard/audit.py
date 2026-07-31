"""Audit logging.

Every security- or data-relevant action (registration, login attempts,
registry mutations, uploads, permission denials) is recorded through
log_event rather than each call site inserting rows directly, so the set of
audited actions stays visible in one place.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_wasteguard.models import AuditLog


def log_event(
    session: Session,
    action: str,
    actor_user_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: str | None = None,
) -> AuditLog:
    entry = AuditLog(
        actor_user_id=actor_user_id,
        action=action,
        resource_type=resource_type,
        resource_id=resource_id,
        details=details,
    )
    session.add(entry)
    session.flush()
    return entry


def list_events_for_actor(session: Session, actor_user_id: str) -> list[AuditLog]:
    return list(
        session.execute(
            select(AuditLog).where(AuditLog.actor_user_id == actor_user_id).order_by(AuditLog.created_at.desc())
        ).scalars()
    )
