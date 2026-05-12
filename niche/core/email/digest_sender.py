"""
Digest email sender — renders and sends the daily email digest.

Uses the configured EmailProvider (EP6). Template rendered with Jinja2.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class DigestSender:
    """Renders the digest email template and sends via the configured provider."""

    MAX_RETRIES = 2

    def __init__(
        self,
        email_provider,
        jinja_env,
        app_url: str,
        feed_id: str,
    ) -> None:
        self.provider = email_provider
        self.env = jinja_env
        self.app_url = app_url
        self.feed_id = feed_id

    def send_to_user(
        self,
        user: Any,
        digest: Any,
        items: list[Any],
        bundle: Any,
        unsubscribe_token: str,
    ) -> bool:
        """Render and send digest email to a single user. Returns True on success."""
        try:
            template = self.env.get_template("email/digest.html")
        except Exception as exc:
            logger.error("Failed to load digest email template: %s", exc)
            return False

        date_str = digest.date
        subject = (
            f"[{date_str}] {bundle.config.name} Brief — {len(items)} items"
        )
        html = template.render(
            bundle=bundle,
            items=items,
            digest=digest,
            user=user,
            app_url=self.app_url,
            unsubscribe_url=f"{self.app_url}/auth/unsubscribe/{unsubscribe_token}",
            date_str=date_str,
        )

        for attempt in range(1, self.MAX_RETRIES + 2):
            try:
                ok = self.provider.send(
                    to=user.email,
                    subject=subject,
                    html_body=html,
                    from_email=bundle.config.from_email,
                )
                if ok:
                    logger.info("Digest email sent to %s", user.email)
                    return True
            except Exception as exc:
                logger.warning(
                    "Email send attempt %d/%d failed for %s: %s",
                    attempt, self.MAX_RETRIES + 1, user.email, exc,
                )
        logger.error("All email attempts failed for user %s", user.id)
        return False
