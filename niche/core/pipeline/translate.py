"""
Translation pipeline stage — stub (EP3).

Full implementation: niche/core/translator/deepl_translator.py (primary)
                     niche/core/translator/haiku_translator.py (fallback)
"""
from __future__ import annotations

import logging
from typing import Optional

from ..models.types import FeedBundle, Item

logger = logging.getLogger(__name__)


def translate(
    items: list[Item],
    bundle: FeedBundle,
    target_language: str = "en",
    translator=None,  # optional Translator instance
) -> list[Item]:
    """Translate non-English items to target_language.

    Items where source_language == target_language are skipped.
    On failure: item.translation_failed = True; never served as translated.

    Returns items with body_translated, title_translated, translation_provider set.
    """
    for item in items:
        if item.is_duplicate:
            continue
        if (item.source_language or "en") == target_language:
            continue  # no translation needed
        if translator is None:
            # Stub: mark as not translated
            item.translation_failed = True
            continue
        try:
            translated_title = translator.translate(item.title or "", target_language)
            translated_body = translator.translate(item.body_raw or "", target_language)
            item.title_translated = translated_title
            item.body_translated = translated_body
            item.translation_provider = translator.provider_name
            item.translation_failed = False
        except Exception as exc:
            logger.warning("Translation failed for item %s: %s", item.id, exc)
            item.translation_failed = True

    translated = sum(1 for i in items if not i.is_duplicate and i.translation_provider)
    logger.info("Translate: %d items translated", translated)
    return items
