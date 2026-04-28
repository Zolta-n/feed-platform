from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, timezone
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

from niche.core.models.types import Item, RawItem

_TRACKING_PARAMS = frozenset([
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "source", "fbclid", "gclid",
])


def dedup(
    raw_items: list[RawItem],
    existing_hashes: set[str],
    feed_id: str,
    run_id: str,
    source_names: dict[str, str] | None = None,
) -> list[Item]:
    """
    Convert RawItems to Items and flag duplicates.
    M1 stub: converts all items, marks none as duplicate (real logic added in M2).
    """
    now = datetime.now(timezone.utc)
    seen_hashes: set[str] = set(existing_hashes)
    items: list[Item] = []

    for raw in raw_items:
        url_hash = _url_hash(raw.url)
        is_dup = url_hash in seen_hashes
        if not is_dup:
            seen_hashes.add(url_hash)

        items.append(
            Item(
                id=_make_id(raw.url, raw.fetched_at),
                feed_id=feed_id,
                url=raw.url,
                url_hash=url_hash,
                title=raw.title,
                title_translated=None,
                body_raw=raw.body[:1000],
                body_translated=None,
                summary=None,
                why_it_matters=None,
                source_id=raw.source_id,
                source_name=(source_names or {}).get(raw.source_id, raw.source_id),
                source_language=raw.language,
                topic_tag=None,
                item_type=None,
                region_tag=None,
                company_tags=[],
                translation_failed=False,
                translation_provider=None,
                relevance_score=0.0,
                published_at=raw.published_at,
                fetched_at=raw.fetched_at,
                run_id=run_id,
                word_count=0,
                read_time_min=0.0,
                is_duplicate=is_dup,
                duplicate_of=None,
            )
        )

    return items


def _normalize_url(url: str) -> str:
    parsed = urlparse(url.lower().strip())
    qs = {k: v for k, v in parse_qs(parsed.query).items() if k not in _TRACKING_PARAMS}
    normalized = parsed._replace(
        scheme=parsed.scheme or "https",
        query=urlencode(qs, doseq=True),
        fragment="",
    )
    return urlunparse(normalized)


def _url_hash(url: str) -> str:
    return hashlib.sha256(_normalize_url(url).encode()).hexdigest()


def _make_id(url: str, fetched_at: datetime) -> str:
    raw = f"{url}:{fetched_at.isoformat()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:32]
