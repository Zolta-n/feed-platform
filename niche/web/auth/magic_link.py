from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from werkzeug.security import check_password_hash, generate_password_hash

logger = logging.getLogger(__name__)

_TOKEN_TTL_MINUTES = 15
_APPROVAL_TOKEN_TTL_HOURS = 72

MIN_PASSWORD_LENGTH = 8
_PASSWORD_RATE_LIMIT = 5
_PASSWORD_RATE_WINDOW_SECONDS = 15 * 60

_password_attempts: dict[str, list[float]] = {}
_password_attempts_lock = threading.Lock()


def hash_password(plain: str) -> str:
    return generate_password_hash(plain)


def verify_password(plain: str, stored_hash: str | None) -> bool:
    if not stored_hash:
        return False
    try:
        return check_password_hash(stored_hash, plain)
    except Exception:
        return False


def validate_password_strength(plain: str) -> str | None:
    """Returns None if OK, otherwise an error message."""
    if len(plain) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    return None


def _now() -> float:
    return time.time()


def password_attempt_blocked(email: str) -> bool:
    cutoff = _now() - _PASSWORD_RATE_WINDOW_SECONDS
    with _password_attempts_lock:
        attempts = [t for t in _password_attempts.get(email, []) if t >= cutoff]
        _password_attempts[email] = attempts
        return len(attempts) >= _PASSWORD_RATE_LIMIT


def record_password_failure(email: str) -> None:
    with _password_attempts_lock:
        _password_attempts.setdefault(email, []).append(_now())


def reset_password_attempts(email: str) -> None:
    with _password_attempts_lock:
        _password_attempts.pop(email, None)


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
