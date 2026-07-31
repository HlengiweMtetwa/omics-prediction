import time

import pytest

from ai_wasteguard import tokens


def test_create_and_decode_round_trip():
    token = tokens.create_access_token("user-123")
    assert tokens.decode_access_token(token) == "user-123"


def test_malformed_token_rejected():
    with pytest.raises(tokens.InvalidToken):
        tokens.decode_access_token("not-a-real-token")


def test_token_signed_with_different_key_rejected(monkeypatch):
    token = tokens.create_access_token("user-123")
    monkeypatch.setattr(tokens, "API_SECRET_KEY", "a-completely-different-key")
    with pytest.raises(tokens.InvalidToken):
        tokens.decode_access_token(token)


def test_expired_token_rejected(monkeypatch):
    monkeypatch.setattr(tokens, "API_TOKEN_EXPIRY_MINUTES", -1)  # already expired
    token = tokens.create_access_token("user-123")
    with pytest.raises(tokens.InvalidToken):
        tokens.decode_access_token(token)
