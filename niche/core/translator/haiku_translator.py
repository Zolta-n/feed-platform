from __future__ import annotations

import json
import logging
from dataclasses import replace

import anthropic

from niche.core.models.types import FeedBundle, Item

logger = logging.getLogger(__name__)

_MAX_BODY_CHARS = 2000
_MAX_TOKENS = 512


class HaikuTranslator:
    def __init__(self, client: anthropic.Anthropic, model: str) -> None:
        self._client = client
        self._model = model

    def translate(
        self, item: Item, bundle: FeedBundle
    ) -> tuple[Item | None, anthropic.types.Usage]:
        """Returns (translated_item, usage). Returns (None, usage) on parse failure."""
        prompt_body = bundle.prompts["translate"]
        static_part = prompt_body.split("{{")[0].strip()
        user_msg = (
            f"Source language: {item.source_language}\n"
            f"Title: {item.title}\n"
            f"Body: {item.body_raw[:_MAX_BODY_CHARS]}"
        )
        response = self._client.messages.create(
            model=self._model,
            max_tokens=_MAX_TOKENS,
            system=[{"type": "text", "text": static_part, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_msg}],
        )
        text = response.content[0].text.strip()
        try:
            data = json.loads(_strip_fence(text))
            title_t = data.get("title", "").strip()
            body_t = data.get("body", "").strip()
            if title_t and body_t:
                return replace(
                    item,
                    title_translated=title_t,
                    body_translated=body_t,
                    translation_provider="haiku",
                ), response.usage
        except (json.JSONDecodeError, AttributeError):
            pass
        logger.warning("item=%s haiku translation parse failure", item.id)
        return None, response.usage


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1
        end = len(lines) - 1 if lines and lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end]).strip()
    return text
