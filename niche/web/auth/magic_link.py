from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)

_TOKEN_TTL_MINUTES = 15
_APPROVAL_TOKEN_TTL_HOURS = 72


def generate_login_token() -> str:
    return secrets.token_hex(32)


def make_login_link(token: str, app_url: str) -> str:
    app_url = app_url.rstrip("/")
    return f"{app_url}/auth/verify?token={token}"


def token_expiry() -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=_TOKEN_TTL_MINUTES)).isoformat()


def is_token_expired(expires_at_iso: str) -> bool:
    expiry = datetime.fromisoformat(expires_at_iso)
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) > expiry


def make_approval_token(user_id: str, secret: str) -> str:
    expiry_ts = int(
        (datetime.now(timezone.utc) + timedelta(hours=_APPROVAL_TOKEN_TTL_HOURS)).timestamp()
    )
    payload = f"{user_id}:{expiry_ts}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{sig}"


def validate_approval_token(token: str, secret: str) -> str | None:
    """Returns user_id if valid, None otherwise."""
    try:
        parts = token.split(":")
        if len(parts) != 3:
            return None
        user_id, expiry_ts_str, sig = parts
        expiry_ts = int(expiry_ts_str)
        payload = f"{user_id}:{expiry_ts}"
        expected_sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected_sig):
            return None
        if datetime.now(timezone.utc).timestamp() > expiry_ts:
            return None
        return user_id
    except Exception:
        return None


def make_unsubscribe_token(user_id: str, secret: str) -> str:
    sig = hmac.new(secret.encode(), f"unsub:{user_id}".encode(), hashlib.sha256).hexdigest()
    return f"{user_id}:{sig}"


def validate_unsubscribe_token(token: str, secret: str) -> str | None:
    try:
        user_id, sig = token.rsplit(":", 1)
        expected = hmac.new(secret.encode(), f"unsub:{user_id}".encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, expected):
            return user_id
    except Exception:
        pass
    return None
