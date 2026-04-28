from __future__ import annotations

import logging
import os
from dataclasses import replace

from niche.core.models.types import FeedBundle, Item

logger = logging.getLogger(__name__)

_STUB_SUMMARY = "Stub summary for synthetic test content."
_STUB_WHY = "Stub why-it-matters for synthetic test content."


def summarize(
    items: list[Item],
    bundle: FeedBundle,
    repo=None,
    run_id: str | None = None,
) -> list[Item]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return _summarize_stub(items, bundle)
    return _summarize_llm(items, bundle, api_key, repo, run_id)


def _summarize_stub(items: list[Item], bundle: FeedBundle) -> list[Item]:
    stub_wc = len(_STUB_SUMMARY.split())
    stub_rt = max(1.0, stub_wc / 200)
    return [
        replace(item, summary=_STUB_SUMMARY, why_it_matters=_STUB_WHY,
                word_count=stub_wc, read_time_min=stub_rt)
        for item in items
    ]


def _summarize_llm(
    items: list[Item],
    bundle: FeedBundle,
    api_key: str,
    repo,
    run_id: str | None,
) -> list[Item]:
    import anthropic
    from niche.core.summarizer.haiku import HaikuSummarizer
    from niche.core.cost.tracker import record_call

    model = bundle.prompt_meta.get("summarize", {}).get("model", "claude-haiku-4-5")
    prompt_version = bundle.prompt_meta.get("summarize", {}).get("version")
    client = anthropic.Anthropic(api_key=api_key)
    summarizer = HaikuSummarizer(client, model)

    result: list[Item] = []
    for item in items:
        updated, usage = summarizer.summarize(item, bundle)

        if usage and repo and run_id:
            record_call(
                repo,
                feed_id=item.feed_id,
                run_id=run_id,
                agent="summarize",
                model=model,
                prompt_name="summarize",
                prompt_version=prompt_version,
                input_tokens=usage.input_tokens,
                output_tokens=usage.output_tokens,
                cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
            )

        if updated is None:
            continue  # excluded from digest per spec
        result.append(updated)

    return result
