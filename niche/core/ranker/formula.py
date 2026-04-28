from __future__ import annotations

from datetime import datetime, timezone

from niche.core.models.types import Item


def score_item(
    item: Item,
    *,
    source_weight: float,
    topic_weight: float,
    company_boost: float,
    thumbs_signal: float = 0.0,
    keyword_blocks: list[str] | None = None,
    keyword_boost_factor: float = 1.0,
) -> float | None:
    """
    Returns relevance score, or None if the item is blocked by a keyword.

    Formula: (source_weight × topic_weight × company_boost) + recency_decay + thumbs_signal
    """
    if keyword_blocks:
        text = f"{item.title} {item.body_raw}".lower()
        for kw in keyword_blocks:
            if kw.lower() in text:
                return None

    recency = _recency_decay(item.published_at)
    raw = (source_weight * topic_weight * company_boost) + recency + thumbs_signal
    return max(0.0, raw) * keyword_boost_factor


def _recency_decay(published_at: datetime | None) -> float:
    if published_at is None:
        return 0.5
    hours_since = (datetime.now(timezone.utc) - published_at).total_seconds() / 3600
    return 1.0 / (1 + hours_since / 24)
