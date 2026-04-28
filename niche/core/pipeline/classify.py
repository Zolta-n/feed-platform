from __future__ import annotations

from dataclasses import replace

from niche.core.models.types import FeedBundle, Item


def classify(items: list[Item], bundle: FeedBundle) -> list[Item]:
    """
    M1 stub: assigns the first valid values from the bundle taxonomy.
    Real LLM-based classification added in M3.
    """
    first_topic = bundle.taxonomy.topics[0].id if bundle.taxonomy.topics else None
    first_type = bundle.taxonomy.item_types[0].id if bundle.taxonomy.item_types else None
    first_region = bundle.taxonomy.regions[0].id if bundle.taxonomy.regions else None

    return [
        replace(
            item,
            topic_tag=first_topic,
            item_type=first_type,
            region_tag=first_region,
            company_tags=[],
        )
        for item in items
        if not item.is_duplicate
    ]
