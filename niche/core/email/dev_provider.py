from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class DevEmailProvider:
    """Logs emails to console instead of sending. Used when RESEND_API_KEY is absent."""

    def send(self, *, to: str, subject: str, html: str, from_email: str) -> None:
        import re
        # Extract the first URL from the HTML for easy copy-paste
        urls = re.findall(r'href="([^"]+)"', html)
        first_url = urls[0] if urls else "(no link found)"
        logger.info(
            "\n--- DEV EMAIL ---\nTo: %s\nSubject: %s\nLink: %s\n--- END ---",
            to, subject, first_url,
        )
        print(f"\n[DEV EMAIL] To={to!r}  Subject={subject!r}\n  Link: {first_url}\n")
