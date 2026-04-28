from __future__ import annotations

import logging
import os

from niche.core.models.types import Cluster, FeedBundle, Item

logger = logging.getLogger(__name__)


def cluster(
    items: list[Item],
    bundle: FeedBundle,
    repo=None,
    run_id: str | None = None,
) -> list[Cluster]:
    from niche.core.clusterer.rule_based import build_clusters

    client = None
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if api_key:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
        except Exception as exc:
            logger.warning("Could not create Anthropic client for clustering: %s", exc)

    return build_clusters(items, bundle, client=client, repo=repo, run_id=run_id)
