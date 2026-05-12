"""
Digest composition pipeline stage (EP3).

Pure function: compose(items, clusters, bundle, run_id, date) -> Digest

Accumulates items up to ~15 minutes read time or 30 items (floor 10).
Ensures at least 1 item from each non-empty cluster.
"""
from __future__ import annotations

import datetime
import json
import logging
import uuid
from dataclasses import asdict
from typing import Optional

from ..models.types import Cluster, Digest, FeedBundle, Item

logger = logging.getLogger(__name__)

MIN_ITEMS = 10
MAX_ITEMS = 30
TARGET_READ_TIME = 15.0  # minutes


def compose(
    items: list[Item],
    clusters: list[Cluster],
    bundle: FeedBundle,
    run_id: Optional[str] = None,
    date: Optional[str] = None,
    user_id: Optional[str] = None,
) -> Digest:
    """Build a Digest from ranked+clustered items.

    Args:
        items: ranked items (highest score first)
        clusters: cluster assignments
        bundle: feed bundle (for feed_id)
        run_id: current pipeline run id
        date: YYYY-MM-DD; defaults to today
        user_id: None for canonical digest; user id for personalised digest

    Returns:
        Digest dataclass (not yet written to DB)
    """
    if not date:
        date = datetime.date.today().isoformat()

    feed_id = bundle.config.feed_id

    # Ensure cluster representation: collect at least 1 item per cluster
    cluster_rep_ids: set[str] = set()
    for cl in clusters:
        if cl.item_ids:
            cluster_rep_ids.add(cl.item_ids[0])

    selected: list[Item] = []
    total_read_time = 0.0
    items_by_id = {i.id: i for i in items}

    # First pass: include cluster representatives
    for item_id in cluster_rep_ids:
        item = items_by_id.get(item_id)
        if item and item.id not in {s.id for s in selected}:
            selected.append(item)
            total_read_time += item.read_time_min

    # Second pass: fill up to MIN_ITEMS / TARGET_READ_TIME / MAX_ITEMS
    for item in items:
        if item.id in {s.id for s in selected}:
            continue
        if len(selected) >= MAX_ITEMS:
            break
        if len(selected) >= MIN_ITEMS and total_read_time >= TARGET_READ_TIME:
            break
        selected.append(item)
        total_read_time += item.read_time_min

    # Sort selected by relevance_score
    selected.sort(key=lambda i: i.relevance_score, reverse=True)

    cluster_map = []
    for cl in clusters:
        cluster_map.append({
            "label": cl.label,
            "item_ids": [i for i in cl.item_ids if i in {s.id for s in selected}],
            "display_order": cl.display_order,
            "lead_blurb": cl.lead_blurb,
        })

    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    digest = Digest(
        id=str(uuid.uuid4()),
        feed_id=feed_id,
        date=date,
        item_ids=[i.id for i in selected],
        cluster_map=cluster_map,
        total_read_time_min=round(total_read_time, 2),
        item_count=len(selected),
        created_at=now,
        user_id=user_id,
        run_id=run_id,
    )

    logger.info(
        "Compose: digest %s — %d items, %.1f min read, %d clusters",
        digest.id, digest.item_count, digest.total_read_time_min, len(clusters),
    )
    return digest
