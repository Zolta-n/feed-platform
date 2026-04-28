from __future__ import annotations
import logging
from niche.core.models.types import FeedBundle, RawItem
from niche.core.sources.factory import build_sources

logger = logging.getLogger(__name__)


def run(bundle: FeedBundle, run_id: str) -> list[RawItem]:
    sources = build_sources(list(bundle.sources))
    raw_items: list[RawItem] = []
    for source in sources:
        fetched = source.fetch()
        logger.info("run_id=%s source=%s fetched=%d", run_id, source.source_id, len(fetched))
        raw_items.extend(fetched)
    return raw_items
