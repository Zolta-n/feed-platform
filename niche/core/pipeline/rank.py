"""
Ranking pipeline stage — delegates to niche/core/ranker/formula.py (EP3, EP8).
"""
from __future__ import annotations

import logging
from typing import Optional

from ..models.types import FeedBundle, Item, Preferences
from ..ranker.formula import compute_score

logger = logging.getLogger(__name__)


def rank(
    items: list[Item],
    bundle: FeedBundle,
    preferences: Optional[Preferences] = None,
    feedback_signals: Optional[dict] = None,
) -> list[Item]:
    """Score and sort items by relevance_score descending.

    Items with no summary are excluded (not renderable).
    Keyword-blocked items are excluded.

    Args:
        items: post-summarize items
        bundle: feed bundle for taxonomy weights
        preferences: user preferences (None = default weights)
        feedback_signals: {topic_tag: net_signal} from feedback table

    Returns:
        sorted list (highest score first), duplicates and summary-less excluded
    """
    keyword_blocks: list[str] = []
    keyword_boosts: list[dict] = []
    if preferences:
        keyword_blocks = preferences.keyword_blocks or []
        keyword_boosts = preferences.keyword_boosts or []

    topic_weights = {}
    if preferences and preferences.topic_weights:
        topic_weights = preferences.topic_weights
    else:
        topic_weights = {t.id: t.weight for t in bundle.taxonomy.topics}

    region_weights = {}
    if preferences and preferences.region_weights:
        region_weights = preferences.region_weights

    company_boosts = {}
    if preferences and preferences.company_boosts:
        company_boosts = preferences.company_boosts

    ranked: list[Item] = []
    for item in items:
        if item.is_duplicate:
            continue
        if not item.summary:
            continue
        # Keyword block check
        text_lower = (item.title or "").lower() + " " + (item.summary or "").lower()
        if any(kw.lower() in text_lower for kw in keyword_blocks):
            logger.debug("Item %s blocked by keyword filter", item.id)
            continue

        item.relevance_score = compute_score(
            item=item,
            topic_weights=topic_weights,
            region_weights=region_weights,
            company_boosts=company_boosts,
            feedback_signals=feedback_signals or {},
            keyword_boosts=keyword_boosts,
        )
        ranked.append(item)

    ranked.sort(key=lambda i: i.relevance_score, reverse=True)
    logger.info("Rank: %d items scored and sorted", len(ranked))
    return ranked
