from __future__ import annotations

import uuid
from datetime import datetime, timezone

from niche.core.models.types import Cluster, Digest, FeedBundle, Item

_DIGEST_MIN_ITEMS = 10
_DIGEST_MAX_ITEMS = 30
_DIGEST_TARGET_MINUTES = 15.0
_MIN_ITEMS_PER_TOPIC = 3


def compose(
    items: list[Item],
    clusters: list[Cluster],
    bundle: FeedBundle,
    run_id: str,
) -> Digest:
    selected = _select_items(items, clusters)
    cluster_map = [
        {"label": c.label, "item_ids": c.item_ids, "display_order": c.display_order}
        for c in clusters
    ]
    now = datetime.now(timezone.utc).isoformat()

    return Digest(
        id=str(uuid.uuid4()),
        feed_id=bundle.config.feed_id,
        user_id=None,
        run_id=run_id,
        date=now[:10],
        item_ids=[item.id for item in selected],
        cluster_map=cluster_map,
        total_read_time_min=sum(item.read_time_min for item in selected),
        item_count=len(selected),
        created_at=now,
        email_sent_at=None,
    )


def _select_items(items: list[Item], clusters: list[Cluster]) -> list[Item]:
    if not items:
        return []

    item_map = {i.id: i for i in items}

    # Step 1: one representative per cluster (highest-ranked = first in cluster.item_ids
    # that appears in items, which are already ranked descending)
    rank_order = {item.id: pos for pos, item in enumerate(items)}
    selected_ids: list[str] = []
    selected_set: set[str] = set()

    for c in clusters:
        for iid in c.item_ids:
            if iid in item_map and iid not in selected_set:
                selected_ids.append(iid)
                selected_set.add(iid)
                break

    # Step 2: per-topic minimum — top-up each topic to _MIN_ITEMS_PER_TOPIC.
    # Items are already in descending rank order, so the first unselected item
    # per topic is always the highest-ranked remaining one.
    by_topic: dict[str, list[str]] = {}
    for item in items:
        if item.topic_tag:
            by_topic.setdefault(item.topic_tag, []).append(item.id)

    for topic_item_ids in by_topic.values():
        already = sum(1 for iid in topic_item_ids if iid in selected_set)
        needed = _MIN_ITEMS_PER_TOPIC - already
        for iid in topic_item_ids:
            if needed <= 0 or len(selected_ids) >= _DIGEST_MAX_ITEMS:
                break
            if iid in selected_set:
                continue
            selected_ids.append(iid)
            selected_set.add(iid)
            needed -= 1

    # Step 3: fill from top-ranked items not already selected
    total_time = sum(item_map[iid].read_time_min for iid in selected_ids if iid in item_map)
    for item in items:
        if len(selected_ids) >= _DIGEST_MAX_ITEMS:
            break
        if item.id in selected_set:
            continue
        selected_ids.append(item.id)
        selected_set.add(item.id)
        total_time += item.read_time_min
        if len(selected_ids) >= _DIGEST_MIN_ITEMS and total_time >= _DIGEST_TARGET_MINUTES:
            break

    # Restore ranking order
    selected_ids.sort(key=lambda iid: rank_order.get(iid, len(items)))
    return [item_map[iid] for iid in selected_ids if iid in item_map]
