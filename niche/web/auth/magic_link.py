"""Magic link token generation and HMAC utilities."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Optional


def generate_magic_token() -> str:
    """Generate a 64-hex-char magic link token."""
    return secrets.token_hex(32)


def generate_hmac_token(data: str, secret: str, expiry_seconds: int = 259200) -> str:
    """Generate an HMAC-signed token with embedded expiry timestamp.

    Format: {timestamp}.{hmac_hex}
    Default expiry: 72 hours (admin approval links).
    """
    ts = int(time.time()) + expiry_seconds
    payload = f"{data}:{ts}"
    sig = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{ts}.{sig}"


def verify_hmac_token(token: str, data: str, secret: str) -> bool:
    """Verify an HMAC token. Returns True if valid and not expired."""
    try:
        ts_str, sig = token.split(".", 1)
        ts = int(ts_str)
    except (ValueError, AttributeError):
        return False
    if int(time.time()) > ts:
        return False  # expired
    payload = f"{data}:{ts}"
    expected = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, sig)


def generate_unsubscribe_token(user_id: str, secret: str) -> str:
    """Generate a permanent (no-expiry) unsubscribe token."""
    sig = hmac.new(
        secret.encode(),
        f"unsub:{user_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{user_id}.{sig}"


def verify_unsubscribe_token(token: str, secret: str) -> Optional[str]:
    """Verify unsubscribe token. Returns user_id on success, None on failure."""
    try:
        user_id, sig = token.rsplit(".", 1)
    except (ValueError, AttributeError):
        return None
    expected = hmac.new(
        secret.encode(),
        f"unsub:{user_id}".encode(),
        hashlib.sha256,
    ).hexdigest()
    if hmac.compare_digest(expected, sig):
        return user_id
    return None
