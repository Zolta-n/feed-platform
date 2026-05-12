from __future__ import annotations

import logging

from niche.core.models.types import FiltersConfig, FiltersRule, Item, RawItem

logger = logging.getLogger(__name__)

_SAMPLE_CAP_PER_RULE = 20


def filter_relevance(
    raw_items: list[RawItem],
    filters: FiltersConfig | None,
) -> tuple[list[RawItem], dict]:
    """Drop off-topic items pre-LLM.

    Returns (surviving_items, stats_dict). When filters is None, the input
    is returned unchanged with an empty stats dict.
    """
    if _no_active_rules(filters):
        return raw_items, {}
    return _apply(raw_items, filters, _raw_haystack)


def filter_items(
    items: list[Item],
    filters: FiltersConfig | None,
) -> tuple[list[Item], dict]:
    """Drop off-topic Items post-translate.

    Used for the rolling pool merge so stale items from before the filter
    existed (or from foreign-language pre-translate over-blocking) get a
    second chance to be evaluated against translated text.
    """
    if _no_active_rules(filters):
        return items, {}
    return _apply(items, filters, _item_haystack)


def _no_active_rules(filters: FiltersConfig | None) -> bool:
    return filters is None or (filters.block is None and filters.require_any is None)


def _apply(items, filters, haystack_fn):
    """Generic block/require_any apply loop, parameterised by haystack extractor."""
    survivors = []
    blocked = 0
    require_missed = 0
    block_samples: list[dict] = []
    require_samples: list[dict] = []

    for item in items:
        block_match = (
            _first_match_in_text(*haystack_fn(item, filters.block), filters.block)
            if filters.block else None
        )
        if block_match is not None:
            blocked += 1
            if len(block_samples) < _SAMPLE_CAP_PER_RULE:
                block_samples.append(
                    {"title": _title_of(item), "matched": block_match, "rule": "block"}
                )
            continue

        if filters.require_any is not None:
            req_match = _first_match_in_text(
                *haystack_fn(item, filters.require_any), filters.require_any
            )
            if req_match is None:
                require_missed += 1
                if len(require_samples) < _SAMPLE_CAP_PER_RULE:
                    require_samples.append(
                        {"title": _title_of(item), "matched": None, "rule": "require_missed"}
                    )
                continue

        survivors.append(item)

    stats = {
        "blocked": blocked,
        "require_missed": require_missed,
        "samples": block_samples + require_samples,
    }
    logger.info(
        "filter: in=%d out=%d blocked=%d require_missed=%d",
        len(items), len(survivors), blocked, require_missed,
    )
    return survivors, stats


def _first_match_in_text(title: str, body: str, rule: FiltersRule) -> str | None:
    """Return the first matching phrase, or None.

    Title and body are passed in already-resolved (post-translation if
    applicable). Caller decides which fields supply each.
    """
    parts: list[str] = []
    if "title" in rule.match_fields:
        parts.append(title or "")
    if "body" in rule.match_fields:
        parts.append(body or "")
    haystack = "\n".join(parts)
    for phrase, pattern in zip(rule.phrases, rule.compiled):
        if pattern.search(haystack):
            return phrase
    return None


def _raw_haystack(item: RawItem, _rule: FiltersRule) -> tuple[str, str]:
    return item.title or "", item.body or ""


def _item_haystack(item: Item, _rule: FiltersRule) -> tuple[str, str]:
    """Prefer translated text — that's where English brake terms appear."""
    title = item.title_translated or item.title or ""
    body = item.body_translated or item.body_raw or ""
    return title, body


def _title_of(item) -> str:
    """Best-effort title for stats sample, regardless of item type."""
    if isinstance(item, Item):
        return item.title_translated or item.title or ""
    return getattr(item, "title", "") or ""
