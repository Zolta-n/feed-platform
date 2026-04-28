from __future__ import annotations
import logging
from niche.core.models.types import FeedBundle
from niche.core.models.repository import Repository

logger = logging.getLogger(__name__)


def run(bundle: FeedBundle, repo: Repository, run_id: str, **kwargs):
    logger.info("run_id=%s agent=classifier (stub)", run_id)
    return None
