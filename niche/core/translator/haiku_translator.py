"""Claude Haiku fallback translation provider (EP6)."""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class HaikuTranslator:
    provider_name = "haiku"

    def __init__(self, anthropic_client, prompt_meta=None) -> None:
        self._client = anthropic_client
        self._prompt_meta = prompt_meta
        self._model = (prompt_meta.model if prompt_meta else "claude-haiku-4-5")

    def translate(self, text: str, target_language: str = "en") -> str:
        if not text.strip():
            return text
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                messages=[{
                    "role": "user",
                    "content": (
                        f"Translate the following text to {target_language}. "
                        f"Return only the translation, no explanation.\n\n{text}"
                    ),
                }],
            )
            return response.content[0].text.strip()
        except Exception as exc:
            logger.error("HaikuTranslator error: %s", exc)
            raise
