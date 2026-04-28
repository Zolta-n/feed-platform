from __future__ import annotations

import uuid
from datetime import datetime, timezone

from niche.core.models.types import Cluster, Digest, FeedBundle, Item

_DIGEST_MIN_ITEMS = 10
_DIGEST_MAX_ITEMS = 30
_DIGEST_TARGET_MINUTES = 15.0


def compose(
    items: list[Item],
    clusters: list[Cluster],
    bundle: FeedBundle,
    run_id: str,
) -> Digest:
    """
    Build a canonical Digest from ranked, clustered items.
    Adaptive sizing: fill ~15 minutes, min 10, max 30 items.
    """
    selected = _select_items(items)
    cluster_map = [
        {"label": c.label, "item_ids": c.item_ids, "display_order": c.display_order}
        for c in clusters
    ]
    now = datetime.now(timezone.utc).isoformat()
    today = now[:10]

    return Digest(
        id=str(uuid.uuid4()),
        feed_id=bundle.config.feed_id,
        user_id=None,
        run_id=run_id,
        date=today,
        item_ids=[item.id for item in selected],
        cluster_map=cluster_map,
        total_read_time_min=sum(item.read_time_min for item in selected),
        item_count=len(selected),
        created_at=now,
        email_sent_at=None,
    )


def _select_items(items: list[Item]) -> list[Item]:
    selected: list[Item] = []
    total_time = 0.0

    for item in items[:_DIGEST_MAX_ITEMS]:
        selected.append(item)
        total_time += item.read_time_min
        if len(selected) >= _DIGEST_MIN_ITEMS and total_time >= _DIGEST_TARGET_MINUTES:
            break

    return selected
