from __future__ import annotations

from dataclasses import replace

from niche.core.models.types import FeedBundle, Item
from niche.core.ranker.formula import score_item


def rank(
    items: list[Item],
    bundle: FeedBundle,
    preferences: dict | None = None,
    repo=None,
) -> list[Item]:
    prefs = preferences or {}
    topic_weights_pref: dict[str, float] = prefs.get("topic_weights", {})
    company_boosts_pref: dict[str, float] = prefs.get("company_boosts", {})
    keyword_blocks: list[str] = prefs.get("keyword_blocks", [])
    keyword_boosts: dict[str, float] = prefs.get("keyword_boosts", {})

    source_weight_map = {s.id: s.source_weight for s in bundle.sources}
    topic_weight_map = {t.id: t.weight for t in bundle.taxonomy.topics}
    if repo:
        try:
            db_entries = repo.get_watchlist_entries(bundle.config.feed_id)
            company_boost_map = {e["id"]: e["boost"] for e in db_entries}
        except Exception:
            company_boost_map = {c.id: c.boost for c in bundle.companies}
    else:
        company_boost_map = {c.id: c.boost for c in bundle.companies}

    ranked: list[Item] = []
    for item in items:
        sw = source_weight_map.get(item.source_id, 1.0)

        # topic_weight: user preference × taxonomy baseline
        base_tw = topic_weight_map.get(item.topic_tag, 1.0)
        tw = topic_weights_pref.get(item.topic_tag, 1.0) * base_tw

        # company_boost: max boost from any tagged company
        if item.company_tags:
            boost = max(
                company_boosts_pref.get(c, company_boost_map.get(c, 1.0))
                for c in item.company_tags
            )
        else:
            boost = 1.0

        # keyword boost factor: first matching keyword wins
        text = f"{item.title} {item.body_raw}".lower()
        kw_factor = 1.0
        for kw, factor in keyword_boosts.items():
            if kw.lower() in text:
                kw_factor = factor
                break

        score = score_item(
            item,
            source_weight=sw,
            topic_weight=tw,
            company_boost=boost,
            thumbs_signal=0.0,  # canonical digest; per-user thumbs deferred to M5
            keyword_blocks=keyword_blocks,
            keyword_boost_factor=kw_factor,
        )

        if score is not None:
            ranked.append(replace(item, relevance_score=score))

    ranked.sort(key=lambda i: i.relevance_score, reverse=True)
    return ranked
