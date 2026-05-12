"""
Classification pipeline stage — stub implementation (EP3).

Full implementation lives in niche/core/classifiers/haiku.py.
This stub applies default_topic/default_region from source config
and does basic string-match company tagging.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from ..models.types import FeedBundle, Item, WatchlistEntry

logger = logging.getLogger(__name__)


def _match_company_tags(
    text: str, watchlist: list[WatchlistEntry]
) -> list[str]:
    """String-match title+body against watchlist names and aliases."""
    matched = []
    lower_text = text.lower()
    for entry in watchlist:
        if not entry.enabled:
            continue
        terms = [entry.name] + entry.aliases
        if any(term.lower() in lower_text for term in terms):
            matched.append(entry.id)
    return matched


def classify(
    items: list[Item],
    bundle: FeedBundle,
    classifier=None,  # optional HaikuClassifier; None uses stub behaviour
) -> list[Item]:
    """Classify topic, item_type, region, and company_tags for each item.

    Args:
        items: non-duplicate items post-dedup
        bundle: feed bundle (taxonomy + watchlist + prompts)
        classifier: optional real classifier; if None, uses default_topic
                    from source config and regex-based company tagging

    Returns:
        items with classification fields populated (or None on failure)
    """
    valid_topic_ids = {t.id for t in bundle.taxonomy.topics}
    valid_region_ids = {r.id for r in bundle.taxonomy.regions}
    valid_type_ids = {it.id for it in bundle.taxonomy.item_types}

    for item in items:
        if item.is_duplicate:
            continue
        search_text = f"{item.title or ''} {item.body_raw or ''}"

        # Company tags — string matching (no LLM)
        item.company_tags = _match_company_tags(search_text, bundle.watchlist)

        if classifier is not None:
            try:
                result = classifier.classify_item(item, bundle)
                if result.get("topic_tag") in valid_topic_ids:
                    item.topic_tag = result["topic_tag"]
                if result.get("item_type") in valid_type_ids:
                    item.item_type = result["item_type"]
                if result.get("region_tag") in valid_region_ids:
                    item.region_tag = result["region_tag"]
            except Exception as exc:
                logger.warning("Classifier failed for item %s: %s", item.id, exc)
        else:
            # Stub: leave topic_tag/region_tag as set by dedup (from source defaults)
            # Validate they're in taxonomy
            if item.topic_tag and item.topic_tag not in valid_topic_ids:
                item.topic_tag = None
            if item.region_tag and item.region_tag not in valid_region_ids:
                item.region_tag = None

    logger.info("Classify: processed %d items", len(items))
    return items
