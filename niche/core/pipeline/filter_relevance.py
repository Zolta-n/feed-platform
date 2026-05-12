from __future__ import annotations

import logging

from niche.core.models.types import FiltersConfig, FiltersRule, RawItem

logger = logging.getLogger(__name__)

_SAMPLE_CAP_PER_RULE = 20


def filter_relevance(
    raw_items: list[RawItem],
    filters: FiltersConfig | None,
) -> tuple[list[RawItem], dict]:
    """Drop off-topic items pre-LLM.

    Returns (surviving_items, stats_dict). When filters is None, the input
    is returned unchanged with an empty stats dict.

    Order of evaluation per item:
      1. If a block phrase matches → drop (recorded under "blocked").
      2. Else if require_any is configured and no required phrase matches →
         drop (recorded under "require_missed").
      3. Else → keep.
    """
    if filters is None or (filters.block is None and filters.require_any is None):
        return raw_items, {}

    survivors: list[RawItem] = []
    blocked = 0
    require_missed = 0
    block_samples: list[dict] = []
    require_samples: list[dict] = []

    for item in raw_items:
        block_match = _first_match(item, filters.block) if filters.block else None
        if block_match is not None:
            blocked += 1
            if len(block_samples) < _SAMPLE_CAP_PER_RULE:
                block_samples.append(
                    {"title": item.title, "matched": block_match, "rule": "block"}
                )
            continue

        if filters.require_any is not None:
            req_match = _first_match(item, filters.require_any)
            if req_match is None:
                require_missed += 1
                if len(require_samples) < _SAMPLE_CAP_PER_RULE:
                    require_samples.append(
                        {"title": item.title, "matched": None, "rule": "require_missed"}
                    )
                continue

        survivors.append(item)

    stats = {
        "blocked": blocked,
        "require_missed": require_missed,
        "samples": block_samples + require_samples,
    }
    logger.info(
        "filter_relevance: in=%d out=%d blocked=%d require_missed=%d",
        len(raw_items), len(survivors), blocked, require_missed,
    )
    return survivors, stats


def _first_match(item: RawItem, rule: FiltersRule) -> str | None:
    """Return the first matching phrase, or None if no rule pattern matches."""
    haystack_parts: list[str] = []
    if "title" in rule.match_fields:
        haystack_parts.append(item.title or "")
    if "body" in rule.match_fields:
        haystack_parts.append(item.body or "")
    haystack = "\n".join(haystack_parts)
    for phrase, pattern in zip(rule.phrases, rule.compiled):
        if pattern.search(haystack):
            return phrase
    return None
