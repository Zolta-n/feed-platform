"""DeepL translation provider (EP6)."""
from __future__ import annotations

import logging
from typing import Optional

logger = logging.getLogger(__name__)

try:
    import deepl
    _HAS_DEEPL = True
except ImportError:
    _HAS_DEEPL = False


class DeepLTranslator:
    provider_name = "deepl"

    def __init__(self, api_key: str) -> None:
        if not _HAS_DEEPL:
            raise ImportError("deepl package not installed")
        self._client = deepl.Translator(api_key)

    def translate(self, text: str, target_language: str = "EN-US") -> str:
        if not text.strip():
            return text
        result = self._client.translate_text(text, target_lang=target_language.upper())
        return result.text

    def translate_batch(self, texts: list[str], target_language: str = "EN-US") -> list[str]:
        if not texts:
            return []
        results = self._client.translate_text(texts, target_lang=target_language.upper())
        return [r.text for r in results]
