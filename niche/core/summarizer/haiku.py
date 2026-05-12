from __future__ import annotations

import json
import logging
from dataclasses import replace

import anthropic

from niche.core.models.types import FeedBundle, Item

logger = logging.getLogger(__name__)

_MAX_BODY_CHARS = 800
_MAX_TOKENS = 700


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
                summary_storage, why, word_count = parsed
                read_time_min = max(1.0, word_count / 200)
                return replace(
                    item,
                    summary=summary_storage,
                    why_it_matters=why,
                    word_count=word_count,
                    read_time_min=read_time_min,
                ), last_usage
            if attempt == 0:
                logger.warning("item=%s summarize parse failure, retrying", item.id)

        logger.error("item=%s summarize failed after 2 attempts", item.id)
        return None, last_usage


def _parse_summary(text: str) -> tuple[str, str, int] | None:
    """Parse the summarizer LLM output.

    Accepts both shapes (v2 preferred, v1 kept for backward compatibility):
      v2: {"key_points": [str, ...], "takeaway": str}
      v1: {"summary": str, "why_it_matters": str}

    Returns (summary_storage, why_it_matters, word_count) on success, or None.
    For v2, summary_storage is json.dumps(key_points) so the templates can
    recognize and render it as a bullet list.
    """
    try:
        data = json.loads(_strip_fence(text))
    except (json.JSONDecodeError, AttributeError):
        return None
    if not isinstance(data, dict):
        return None

    # v2 shape
    key_points = data.get("key_points")
    takeaway = (data.get("takeaway") or "").strip()
    if isinstance(key_points, list) and takeaway:
        cleaned = [str(p).strip() for p in key_points if str(p).strip()]
        if cleaned:
            joined = " ".join(cleaned)
            return json.dumps(cleaned), takeaway, len(joined.split())

    # v1 fallback
    summary = (data.get("summary") or "").strip()
    why = (data.get("why_it_matters") or "").strip()
    if summary and why:
        return summary, why, len(summary.split())

    return None


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "```":
                return "\n".join(lines[1:i]).strip()
        text = "\n".join(lines[1:]).strip()
    return text
