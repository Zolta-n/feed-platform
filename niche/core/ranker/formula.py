"""
Ranker scoring formula (EP8).

score = (source_weight × topic_weight × company_boost)
        + recency_decay
        + thumbs_signal

All weights come from taxonomy/preferences — no domain logic here.
"""
from __future__ import annotations

import datetime
import logging
import math
from typing import Optional

from ..models.types import Item

logger = logging.getLogger(__name__)


def _recency_decay(published_at: Optional[str]) -> float:
    """1.0 / (1 + hours_since_published / 24) — halves every 24 hours."""
    if not published_at:
        return 0.5  # neutral for items without a publish date
    try:
        pub = datetime.datetime.fromisoformat(published_at.replace("Z", "+00:00"))
        if pub.tzinfo is None:
            pub = pub.replace(tzinfo=datetime.timezone.utc)
        now = datetime.datetime.now(datetime.timezone.utc)
        hours = max(0, (now - pub).total_seconds() / 3600)
        return 1.0 / (1 + hours / 24)
    except Exception:
        return 0.5


def compute_score(
    item: Item,
    topic_weights: dict[str, float],
    region_weights: dict[str, float],
    company_boosts: dict[str, float],
    feedback_signals: dict[str, float],
    keyword_boosts: list[dict],
    source_weight: float = 1.0,
) -> float:
    """Compute relevance_score for a single item.

    Args:
        item: the item to score
        topic_weights: {topic_id: weight} from preferences/taxonomy
        region_weights: {region_id: weight} from preferences
        company_boosts: {company_slug: boost} from preferences
        feedback_signals: {topic_tag: net_signal} accumulated from feedback table
        keyword_boosts: list of {term: str, weight: float}
        source_weight: from sources table

    Returns:
        relevance_score (float)
    """
    # Topic weight
    topic_weight = topic_weights.get(item.topic_tag or "", 1.0)

    # Region weight
    region_weight = region_weights.get(item.region_tag or "", 1.0)

    # Company boost — max of matching company boosts, else 1.0
    cb = 1.0
    if item.company_tags and company_boosts:
        boosts = [company_boosts[c] for c in item.company_tags if c in company_boosts]
        if boosts:
            cb = max(boosts)

    # Base score
    score = source_weight * topic_weight * region_weight * cb

    # Recency decay
    score += _recency_decay(item.published_at)

    # Thumbs signal (capped at ±0.5)
    ts = feedback_signals.get(item.topic_tag or "", 0.0)
    ts = max(-0.5, min(0.5, ts))
    score += ts

    # Keyword boosts
    text_lower = (item.title or "").lower() + " " + (item.summary or "").lower()
    for kb in keyword_boosts:
        term = kb.get("term", "")
        weight = float(kb.get("weight", 1.0))
        if term and term.lower() in text_lower:
            score *= weight

    return round(score, 4)
