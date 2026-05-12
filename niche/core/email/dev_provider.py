"""Dev email provider — logs to console instead of sending real emails."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class DevEmailProvider:
    """Logs emails to the console. Used in development / tests."""
    provider_name = "dev"

    def send(
        self,
        to: str,
        subject: str,
        html_body: str,
        from_email: str = "noreply@localhost",
        text_body: str = "",
    ) -> bool:
        logger.info(
            "[DevEmail] To: %s | Subject: %s | Body length: %d",
            to, subject, len(html_body),
        )
        return True

    def send_bulk(self, messages: list[dict]) -> list[bool]:
        return [self.send(**m) for m in messages]
