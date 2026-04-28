from __future__ import annotations

import logging
import os

from niche.core.models.types import FeedBundle
from niche.core.models.repository import Repository

logger = logging.getLogger(__name__)


def run(bundle: FeedBundle, repo: Repository, run_id: str, **kwargs):
    """Send the latest digest to eligible subscribers.

    Reads email_provider and app_url from kwargs (passed by scheduler) or
    falls back to env-based construction so the CLI agent command works standalone.
    """
    from niche.core.email.digest_sender import send_digest

    email_provider = kwargs.get("email_provider")
    if email_provider is None:
        resend_key = os.environ.get("RESEND_API_KEY")
        if resend_key:
            from niche.core.email.resend_provider import ResendProvider
            email_provider = ResendProvider(resend_key)
        else:
            from niche.core.email.dev_provider import DevEmailProvider
            email_provider = DevEmailProvider()

    app_url = kwargs.get("app_url") or os.environ.get("APP_URL", "http://localhost:5000")

    sent = send_digest(bundle, repo, email_provider, app_url)
    logger.info("run_id=%s agent=sender sent=%d", run_id, sent)
    return sent
