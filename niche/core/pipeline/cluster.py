from __future__ import annotations

from niche.core.models.types import Cluster, FeedBundle, Item


def cluster(items: list[Item], bundle: FeedBundle) -> list[Cluster]:
    """
    M1 stub: returns a single cluster containing all items.
    Real tag-overlap clustering added in M4.
    """
    if not items:
        return []
    return [Cluster(label="All", item_ids=[item.id for item in items], display_order=0)]
