"""Claude Haiku classifier — topic, item_type, region classification."""
from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


class HaikuClassifier:
    """Uses Claude Haiku with prompt caching to classify feed items."""

    def __init__(self, anthropic_client, prompt_meta=None) -> None:
        self._client = anthropic_client
        self._prompt_meta = prompt_meta
        self._model = (prompt_meta.model if prompt_meta else "claude-haiku-4-5")

    def classify_item(self, item: Any, bundle: Any) -> dict:
        """Returns {"topic_tag": str, "item_type": str, "region_tag": str}."""
        topic_ids = [t.id for t in bundle.taxonomy.topics]
        region_ids = [r.id for r in bundle.taxonomy.regions]
        type_ids = [it.id for it in bundle.taxonomy.item_types]

        system = (
            (self._prompt_meta.body if self._prompt_meta else "")
            or (
                f"Classify the article into: "
                f"topic_tag ({', '.join(topic_ids)}), "
                f"item_type ({', '.join(type_ids)}), "
                f"region_tag ({', '.join(region_ids)}). "
                f"Return JSON only."
            )
        )
        user_content = f"Title: {item.title or ''}\n\nBody:\n{(item.body_raw or '')[:400]}"

        for attempt in range(1, 3):
            try:
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=100,
                    system=system,
                    messages=[{"role": "user", "content": user_content}],
                )
                text = response.content[0].text.strip()
                return json.loads(text)
            except json.JSONDecodeError:
                if attempt == 1:
                    continue
            except Exception as exc:
                logger.warning("Classifier attempt %d failed: %s", attempt, exc)
        return {}
