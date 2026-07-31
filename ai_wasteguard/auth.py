"""Canonical authentication service.

All authentication in the platform must go through this module rather than
duplicating password/session logic elsewhere.
"""
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_wasteguard.config import ACCOUNT_LOCKOUT_MINUTES, ACCOUNT_LOCKOUT_THRESHOLD
from ai_wasteguard.models import AccountStatus, User, UserRole

_hasher = PasswordHasher()


def _as_aware_utc(value: datetime | None) -> datetime | None:
    """SQLite does not persist tzinfo, so a DateTime(timezone=True) value
    read back from it comes out naive even though it was written as UTC.
    Treat any naive value as UTC rather than letting aware/naive comparisons
    raise."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class AuthError(Exception):
    """Base class for authentication failures."""


class EmailAlreadyRegistered(AuthError):
    pass


class InvalidCredentials(AuthError):
    """Raised for both 'no such user' and 'wrong password' - do not
    distinguish these in messages shown to the caller, to avoid leaking
    which emails are registered."""


class AccountDisabled(AuthError):
    pass


class AccountLocked(AuthError):
    pass


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False


def register_user(
    session: Session,
    full_name: str,
    email: str,
    password: str,
    institution: str | None = None,
    role: UserRole = UserRole.RESEARCHER,
) -> User:
    normalized_email = normalize_email(email)
    existing = session.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()
    if existing is not None:
        raise EmailAlreadyRegistered(f"An account already exists for {normalized_email}.")

    user = User(
        full_name=full_name,
        email=normalized_email,
        institution=institution,
        role=role,
        password_hash=hash_password(password),
        status=AccountStatus.ACTIVE,
    )
    session.add(user)
    session.flush()
    return user


def authenticate_user(session: Session, email: str, password: str) -> User:
    normalized_email = normalize_email(email)
    user = session.execute(select(User).where(User.email == normalized_email)).scalar_one_or_none()

    if user is None:
        # Deliberately identical to the wrong-password path below.
        raise InvalidCredentials("Incorrect email or password.")

    if user.status == AccountStatus.DISABLED:
        raise AccountDisabled("This account has been disabled.")

    now = datetime.now(timezone.utc)
    locked_until = _as_aware_utc(user.locked_until)
    if locked_until is not None and locked_until > now:
        raise AccountLocked(f"Account locked until {locked_until.isoformat()}.")

    if not verify_password(user.password_hash, password):
        user.failed_login_count += 1
        if user.failed_login_count >= ACCOUNT_LOCKOUT_THRESHOLD:
            user.locked_until = now + timedelta(minutes=ACCOUNT_LOCKOUT_MINUTES)
        session.flush()
        raise InvalidCredentials("Incorrect email or password.")

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    session.flush()
    return user
