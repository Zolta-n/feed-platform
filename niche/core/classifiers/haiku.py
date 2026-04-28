from __future__ import annotations

import json
import logging

import anthropic

from niche.core.models.types import FeedBundle, Item

logger = logging.getLogger(__name__)


class HaikuClassifier:
    def __init__(self, client: anthropic.Anthropic, model: str) -> None:
        self._client = client
        self._model = model

    def classify_topic(
        self, item: Item, bundle: FeedBundle
    ) -> tuple[str | None, anthropic.types.Usage]:
        prompt_body = bundle.prompts["classify-topic"]
        static_part = prompt_body.split("{{")[0].strip()
        topic_ids = {t.id for t in bundle.taxonomy.topics}

        response = self._client.messages.create(
            model=self._model,
            max_tokens=64,
            system=[{"type": "text", "text": static_part, "cache_control": {"type": "ephemeral"}}],
            messages=[{
                "role": "user",
                "content": f"Article title: {item.title}\nArticle body: {item.body_raw[:500]}",
            }],
        )
        text = response.content[0].text.strip()
        topic = _parse_json_field(text, "topic", item.id, "classify-topic")
        if topic not in topic_ids:
            if topic is not None:
                logger.warning("item=%s classify-topic unknown topic %r", item.id, topic)
            topic = None
        return topic, response.usage

    def classify_item_type(
        self, item: Item, bundle: FeedBundle
    ) -> tuple[str | None, anthropic.types.Usage]:
        prompt_body = bundle.prompts["classify-item-type"]
        static_part = prompt_body.split("{{")[0].strip()
        type_ids = {t.id for t in bundle.taxonomy.item_types}

        response = self._client.messages.create(
            model=self._model,
            max_tokens=32,
            system=[{"type": "text", "text": static_part, "cache_control": {"type": "ephemeral"}}],
            messages=[{
                "role": "user",
                "content": f"Article title: {item.title}",
            }],
        )
        text = response.content[0].text.strip()
        item_type = _parse_json_field(text, "item_type", item.id, "classify-item-type")
        if item_type not in type_ids:
            if item_type is not None:
                logger.warning("item=%s classify-item-type unknown type %r", item.id, item_type)
            item_type = None
        return item_type, response.usage


def _parse_json_field(text: str, field: str, item_id: str, prompt_name: str) -> str | None:
    try:
        return json.loads(_strip_fence(text)).get(field)
    except (json.JSONDecodeError, AttributeError):
        logger.warning("item=%s %s invalid JSON: %r", item_id, prompt_name, text)
        return None


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        # Find first closing fence after the opening line (model may append reasoning after it)
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "```":
                return "\n".join(lines[1:i]).strip()
        text = "\n".join(lines[1:]).strip()
    return text
