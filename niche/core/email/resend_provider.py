from __future__ import annotations

import logging
import time

import resend

logger = logging.getLogger(__name__)

_MAX_RETRIES = 2
_RETRY_DELAY = 2.0


class ResendProvider:
    def __init__(self, api_key: str) -> None:
        resend.api_key = api_key

    def send(self, *, to: str, subject: str, html: str, from_email: str) -> None:
        last_exc: Exception | None = None
        for attempt in range(_MAX_RETRIES + 1):
            try:
                resend.Emails.send({
                    "from": from_email,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                })
                return
            except Exception as exc:
                last_exc = exc
                if attempt < _MAX_RETRIES:
                    time.sleep(_RETRY_DELAY)
                    logger.warning("resend attempt %d failed: %s", attempt + 1, exc)
        logger.error("resend all retries exhausted for %s: %s", to, last_exc)
        raise RuntimeError(f"Email send failed after {_MAX_RETRIES + 1} attempts") from last_exc
