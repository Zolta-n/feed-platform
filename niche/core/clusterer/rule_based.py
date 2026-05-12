"""
Rule-based clusterer — groups items by topic_tag + company tag overlap (EP3).

Target: 3–5 clusters. Items with no topic go into a catch-all cluster.
Minimum cluster size: 2. Singletons merged into catch-all.
"""
from __future__ import annotations

import logging
from typing import Optional

from ..models.types import Cluster, FeedBundle, Item

logger = logging.getLogger(__name__)

TARGET_MIN_CLUSTERS = 3
TARGET_MAX_CLUSTERS = 5
MIN_CLUSTER_SIZE = 2


def cluster_items(items: list[Item], bundle: FeedBundle) -> list[Cluster]:
    """Group items into thematic clusters using tag overlap.

    Returns clusters ordered by sum of relevance_score (highest first).
    """
    if not items:
        return []

    # Build initial clusters: group by (topic_tag, frozenset(company_tags))
    # Items with no company tags cluster by topic_tag alone
    cluster_map: dict[str, list[Item]] = {}
    for item in items:
        if item.company_tags:
            # Use the first company tag as the cluster key within a topic
            key = f"{item.topic_tag or 'other'}:{sorted(item.company_tags)[0]}"
        else:
            key = item.topic_tag or "other"
        cluster_map.setdefault(key, []).append(item)

    # Merge singletons into their topic bucket
    topic_buckets: dict[str, list[Item]] = {}
    for key, members in cluster_map.items():
        if len(members) < MIN_CLUSTER_SIZE:
            topic = key.split(":")[0]
            topic_buckets.setdefault(topic, []).extend(members)
        else:
            topic_buckets.setdefault(key, []).extend(members)

    # Merge small topic buckets together until we have ≤ TARGET_MAX_CLUSTERS
    clusters_list = sorted(
        topic_buckets.items(),
        key=lambda kv: sum(i.relevance_score for i in kv[1]),
        reverse=True,
    )
    while len(clusters_list) > TARGET_MAX_CLUSTERS:
        # Merge the two smallest into the second-to-last
        clusters_list.sort(key=lambda kv: len(kv[1]))
        key0, items0 = clusters_list.pop(0)
        if clusters_list:
            key1, items1 = clusters_list[0]
            clusters_list[0] = (key1, items1 + items0)
        else:
            clusters_list.append((key0, items0))

    # Build Cluster objects
    results: list[Cluster] = []
    for display_order, (key, members) in enumerate(
        sorted(clusters_list, key=lambda kv: sum(i.relevance_score for i in kv[1]), reverse=True)
    ):
        # Human-readable label: look up topic label from taxonomy
        topic_part = key.split(":")[0]
        label = topic_part.replace("-", " ").title()
        for t in bundle.taxonomy.topics:
            if t.id == topic_part:
                label = t.label
                break
        results.append(Cluster(
            label=label,
            item_ids=[i.id for i in sorted(members, key=lambda x: x.relevance_score, reverse=True)],
            display_order=display_order,
        ))

    logger.info("Clusterer: %d items -> %d clusters", len(items), len(results))
    return results
