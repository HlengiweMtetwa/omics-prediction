"""API access tokens (JWT), independent of the Streamlit session/cookie
mechanism used by app_state.py. The API is a second presentation layer and
needs its own stateless auth - it must not share Streamlit's session state.
"""
from datetime import datetime, timedelta, timezone

import jwt

from ai_wasteguard.config import API_SECRET_KEY, API_TOKEN_EXPIRY_MINUTES

ALGORITHM = "HS256"


class InvalidToken(Exception):
    pass


def create_access_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": now,
        "exp": now + timedelta(minutes=API_TOKEN_EXPIRY_MINUTES),
    }
    return jwt.encode(payload, API_SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> str:
    """Returns the user id encoded in the token. Raises InvalidToken for
    anything expired, malformed, or signed with a different key."""
    try:
        payload = jwt.decode(token, API_SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.PyJWTError as exc:
        raise InvalidToken(str(exc)) from exc
    return payload["sub"]
