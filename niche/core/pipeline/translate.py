from __future__ import annotations

import logging
import os
from dataclasses import replace

from niche.core.models.types import FeedBundle, Item

logger = logging.getLogger(__name__)


def translate(
    items: list[Item],
    bundle: FeedBundle,
    repo=None,
    run_id: str | None = None,
) -> list[Item]:
    english = [i for i in items if i.source_language == "en"]
    non_english = [i for i in items if i.source_language != "en"]

    if not non_english:
        return items

    deepl_key = os.environ.get("DEEPL_API_KEY")
    anthropic_key = os.environ.get("ANTHROPIC_API_KEY")

    if not deepl_key and not anthropic_key:
        failed = [replace(i, translation_failed=True) for i in non_english]
        return english + failed

    translated = _translate_items(non_english, bundle, deepl_key, anthropic_key, repo, run_id)
    return english + translated


def _translate_items(
    items: list[Item],
    bundle: FeedBundle,
    deepl_key: str | None,
    anthropic_key: str | None,
    repo,
    run_id: str | None,
) -> list[Item]:
    from niche.core.cost.tracker import record_call

    deepl_translator = None
    haiku_translator = None
    haiku_client = None

    if deepl_key:
        from niche.core.translator.deepl_translator import DeepLTranslator
        deepl_translator = DeepLTranslator(deepl_key)

    if anthropic_key:
        import anthropic as _anthropic
        from niche.core.translator.haiku_translator import HaikuTranslator
        haiku_model = bundle.prompt_meta.get("translate", {}).get("model", "claude-haiku-4-5")
        haiku_client = _anthropic.Anthropic(api_key=anthropic_key)
        haiku_translator = HaikuTranslator(haiku_client, haiku_model)

    result: list[Item] = []
    for item in items:
        translated_item = None

        if deepl_translator:
            try:
                translated_item, char_count = deepl_translator.translate(item)
                if repo and run_id:
                    repo.insert_llm_cost(
                        feed_id=item.feed_id,
                        run_id=run_id,
                        agent="translate",
                        model="deepl",
                        prompt_name=None,
                        prompt_version=None,
                        input_tokens=char_count,
                        output_tokens=0,
                        cache_read_tokens=0,
                        cache_write_tokens=0,
                        usd=0.0,
                    )
            except Exception as exc:
                logger.warning("item=%s deepl failed: %s", item.id, exc)

        if translated_item is None and haiku_translator:
            try:
                translated_item, usage = haiku_translator.translate(item, bundle)
                if usage and repo and run_id:
                    haiku_model = bundle.prompt_meta.get("translate", {}).get("model", "claude-haiku-4-5")
                    prompt_version = bundle.prompt_meta.get("translate", {}).get("version")
                    record_call(
                        repo,
                        feed_id=item.feed_id,
                        run_id=run_id,
                        agent="translate",
                        model=haiku_model,
                        prompt_name="translate",
                        prompt_version=prompt_version,
                        input_tokens=usage.input_tokens,
                        output_tokens=usage.output_tokens,
                        cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                        cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
                    )
            except Exception as exc:
                logger.warning("item=%s haiku translation failed: %s", item.id, exc)

        if translated_item is None:
            result.append(replace(item, translation_failed=True))
        else:
            result.append(translated_item)

    return result
