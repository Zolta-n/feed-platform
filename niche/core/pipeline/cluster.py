"""
Clustering pipeline stage — delegates to niche/core/clusterer/rule_based.py (EP3).
"""
from __future__ import annotations

import logging

from ..clusterer.rule_based import cluster_items
from ..models.types import Cluster, FeedBundle, Item

logger = logging.getLogger(__name__)


def cluster(
    items: list[Item],
    bundle: FeedBundle,
    labeler=None,  # optional Sonnet labeler
) -> tuple[list[Item], list[Cluster]]:
    """Group items into thematic clusters.

    Args:
        items: ranked items (post-rank)
        bundle: feed bundle for taxonomy
        labeler: optional Sonnet call for cluster labels; if None, uses topic_tag

    Returns:
        (items unchanged, list[Cluster] in display order)
    """
    clusters = cluster_items(items, bundle)

    if labeler is not None:
        try:
            clusters = labeler.generate_labels(clusters, items, bundle)
        except Exception as exc:
            logger.warning(
                "Cluster labeler failed, using topic_tag labels: %s", exc
            )

    logger.info("Cluster: produced %d clusters", len(clusters))
    return items, clusters
