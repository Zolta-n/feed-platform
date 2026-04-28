from __future__ import annotations

import json
import logging
from dataclasses import replace

import anthropic

from niche.core.models.types import FeedBundle, Item

logger = logging.getLogger(__name__)

_MAX_BODY_CHARS = 800
_MAX_TOKENS = 256


class HaikuSummarizer:
    def __init__(self, client: anthropic.Anthropic, model: str) -> None:
        self._client = client
        self._model = model

    def summarize(
        self, item: Item, bundle: FeedBundle
    ) -> tuple[Item | None, anthropic.types.Usage | None]:
        """Returns (updated_item, usage) on success, (None, usage) if both attempts fail."""
        prompt_body = bundle.prompts["summarize"]
        static_part = prompt_body.split("{{")[0].strip()
        user_msg = f"Article title: {item.title}\nArticle body: {item.body_raw[:_MAX_BODY_CHARS]}"

        last_usage = None
        for attempt in range(2):
            response = self._client.messages.create(
                model=self._model,
                max_tokens=_MAX_TOKENS,
                system=[{"type": "text", "text": static_part, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user_msg}],
            )
            last_usage = response.usage
            text = response.content[0].text.strip()
            parsed = _parse_summary(text)
            if parsed:
                summary, why = parsed
                word_count = len(summary.split())
                read_time_min = max(1.0, word_count / 200)
                return replace(
                    item,
                    summary=summary,
                    why_it_matters=why,
                    word_count=word_count,
                    read_time_min=read_time_min,
                ), last_usage
            if attempt == 0:
                logger.warning("item=%s summarize parse failure, retrying", item.id)

        logger.error("item=%s summarize failed after 2 attempts", item.id)
        return None, last_usage


def _parse_summary(text: str) -> tuple[str, str] | None:
    try:
        data = json.loads(_strip_fence(text))
        summary = data.get("summary", "").strip()
        why = data.get("why_it_matters", "").strip()
        if summary and why:
            return summary, why
    except (json.JSONDecodeError, AttributeError):
        pass
    return None


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1
        end = len(lines) - 1 if lines and lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end]).strip()
    return text
