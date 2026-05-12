"""Claude Haiku summarizer — produces summary + why_it_matters per item."""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class HaikuSummarizer:
    """Calls Claude Haiku to generate summary and why_it_matters fields."""

    def __init__(self, anthropic_client, prompt_meta=None) -> None:
        self._client = anthropic_client
        self._prompt_meta = prompt_meta
        self._model = (prompt_meta.model if prompt_meta else "claude-haiku-4-5")

    def summarize(self, item: Any, bundle: Any) -> dict:
        """Returns {"summary": str, "why_it_matters": str}."""
        prompt = (
            self._prompt_meta.body
            if self._prompt_meta
            else "Summarize this article in 2-3 sentences and explain why it matters."
        )
        body = item.body_translated or item.body_raw or ""
        user_content = f"Title: {item.title or ''}\n\nBody:\n{body[:1500]}"

        for attempt in range(1, 3):
            try:
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=300,
                    system=prompt,
                    messages=[{"role": "user", "content": user_content}],
                )
                text = response.content[0].text.strip()
                # Try to parse JSON; if not, use as-is for summary
                try:
                    parsed = json.loads(text)
                    return {
                        "summary": parsed.get("summary", ""),
                        "why_it_matters": parsed.get("why_it_matters", ""),
                    }
                except json.JSONDecodeError:
                    return {"summary": text[:400], "why_it_matters": ""}
            except Exception as exc:
                logger.warning(
                    "Summarizer attempt %d failed for item %s: %s",
                    attempt, item.id, exc,
                )
        raise RuntimeError(f"Summarizer failed after 2 attempts for item {item.id}")
