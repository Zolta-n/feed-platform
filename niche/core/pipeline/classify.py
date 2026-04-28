from __future__ import annotations

import logging
import os
from dataclasses import replace

from niche.core.models.types import FeedBundle, Item

logger = logging.getLogger(__name__)


def classify(
    items: list[Item],
    bundle: FeedBundle,
    repo=None,
    run_id: str | None = None,
) -> list[Item]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _classify_stub(items, bundle)
    return _classify_llm(items, bundle, api_key, repo, run_id)


def _classify_stub(items: list[Item], bundle: FeedBundle) -> list[Item]:
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


def _classify_llm(
    items: list[Item],
    bundle: FeedBundle,
    api_key: str,
    repo,
    run_id: str | None,
) -> list[Item]:
    import anthropic
    from niche.core.classifiers.haiku import HaikuClassifier
    from niche.core.cost.tracker import record_call

    model = bundle.prompt_meta.get("classify-topic", {}).get("model", "claude-haiku-4-5")
    topic_version = bundle.prompt_meta.get("classify-topic", {}).get("version")
    type_version = bundle.prompt_meta.get("classify-item-type", {}).get("version")

    client = anthropic.Anthropic(api_key=api_key)
    classifier = HaikuClassifier(client, model)

    result: list[Item] = []
    for item in items:
        if item.is_duplicate:
            continue

        topic, topic_usage = classifier.classify_topic(item, bundle)
        item_type, type_usage = classifier.classify_item_type(item, bundle)
        region = _classify_region(item, bundle)
        companies = _tag_companies(item, bundle)

        if repo and run_id:
            record_call(
                repo,
                feed_id=item.feed_id,
                run_id=run_id,
                agent="classify",
                model=model,
                prompt_name="classify-topic",
                prompt_version=topic_version,
                input_tokens=topic_usage.input_tokens,
                output_tokens=topic_usage.output_tokens,
                cache_read_tokens=getattr(topic_usage, "cache_read_input_tokens", 0) or 0,
                cache_write_tokens=getattr(topic_usage, "cache_creation_input_tokens", 0) or 0,
            )
            record_call(
                repo,
                feed_id=item.feed_id,
                run_id=run_id,
                agent="classify",
                model=model,
                prompt_name="classify-item-type",
                prompt_version=type_version,
                input_tokens=type_usage.input_tokens,
                output_tokens=type_usage.output_tokens,
                cache_read_tokens=getattr(type_usage, "cache_read_input_tokens", 0) or 0,
                cache_write_tokens=getattr(type_usage, "cache_creation_input_tokens", 0) or 0,
            )

        result.append(replace(
            item,
            topic_tag=topic,
            item_type=item_type,
            region_tag=region,
            company_tags=companies,
        ))

    return result


def _classify_region(item: Item, bundle: FeedBundle) -> str | None:
    text = f"{item.title} {item.body_raw}".lower()
    for region in bundle.taxonomy.regions:
        if region.label.lower() in text or region.id.lower() in text:
            return region.id
    return None


def _tag_companies(item: Item, bundle: FeedBundle) -> list[str]:
    text = f"{item.title} {item.body_raw}".lower()
    tags: list[str] = []
    for company in bundle.companies:
        names = [company.name] + list(company.aliases)
        if any(n.lower() in text for n in names):
            tags.append(company.id)
    return tags
