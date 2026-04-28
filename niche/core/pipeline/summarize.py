from __future__ import annotations

from dataclasses import replace

from niche.core.models.types import FeedBundle, Item

_STUB_SUMMARY = "Stub summary for synthetic test content."
_STUB_WHY = "Stub why-it-matters blurb."
_STUB_WORD_COUNT = 6
_STUB_READ_TIME = round(_STUB_WORD_COUNT / 200, 4)


def summarize(items: list[Item], bundle: FeedBundle) -> list[Item]:
    """
    M1 stub: assigns fixed summary fields.
    Real Haiku summarization added in M4.
    """
    return [
        replace(
            item,
            summary=_STUB_SUMMARY,
            why_it_matters=_STUB_WHY,
            word_count=_STUB_WORD_COUNT,
            read_time_min=_STUB_READ_TIME,
        )
        for item in items
    ]
