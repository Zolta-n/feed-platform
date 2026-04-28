from __future__ import annotations

import logging
from dataclasses import replace

import deepl

from niche.core.models.types import Item

logger = logging.getLogger(__name__)

_TARGET_LANG = "EN-US"
_MAX_BODY_CHARS = 2000


class DeepLTranslator:
    def __init__(self, api_key: str) -> None:
        self._client = deepl.Translator(api_key)

    def translate(self, item: Item) -> tuple[Item, int]:
        """Returns (translated_item, char_count). Raises on failure."""
        texts = [item.title, item.body_raw[:_MAX_BODY_CHARS]]
        char_count = sum(len(t) for t in texts)
        results = self._client.translate_text(texts, target_lang=_TARGET_LANG)
        return replace(
            item,
            title_translated=results[0].text,
            body_translated=results[1].text,
            translation_provider="deepl",
        ), char_count
