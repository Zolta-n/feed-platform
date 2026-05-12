"""
Summarization pipeline stage — stub (EP3).

Full implementation: niche/core/summarizer/haiku.py
"""
from __future__ import annotations

import logging

from ..models.types import FeedBundle, Item

logger = logging.getLogger(__name__)


def summarize(
    items: list[Item],
    bundle: FeedBundle,
    summarizer=None,  # optional HaikuSummarizer instance
) -> list[Item]:
    """Produce summary + why_it_matters for each non-duplicate item.

    Items without a summary after this stage are excluded from ranking.
    word_count and read_time_min are computed here.

    Returns items with summary, why_it_matters, word_count, read_time_min set.
    """
    for item in items:
        if item.is_duplicate:
            continue
        if summarizer is not None:
            try:
                result = summarizer.summarize(item, bundle)
                item.summary = result.get("summary", "")
                item.why_it_matters = result.get("why_it_matters", "")
            except Exception as exc:
                logger.warning("Summarizer failed for item %s: %s", item.id, exc)
                item.summary = None
                item.why_it_matters = None
        else:
            # Stub: use body_raw as summary if present, else title
            body = item.body_translated or item.body_raw or item.title or ""
            item.summary = body[:280] if body else None
            item.why_it_matters = "Relevant to feed topics."

        if item.summary:
            item.word_count = len(item.summary.split())
            item.read_time_min = max(0.5, item.word_count / 200)
        else:
            item.word_count = 0
            item.read_time_min = 0.0

    with_summary = sum(1 for i in items if not i.is_duplicate and i.summary)
    logger.info("Summarize: %d/%d items have summaries",
                with_summary, sum(1 for i in items if not i.is_duplicate))
    return items
