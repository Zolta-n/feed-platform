from __future__ import annotations

from dataclasses import replace

from niche.core.models.types import FeedBundle, Item


def rank(
    items: list[Item],
    bundle: FeedBundle,
    preferences: dict | None = None,
) -> list[Item]:
    """
    M1 stub: assigns uniform score of 1.0, preserves order.
    Real formula (source_weight × topic_weight × company_boost + recency + thumbs) added in M4.
    """
    return [replace(item, relevance_score=1.0) for item in items]
