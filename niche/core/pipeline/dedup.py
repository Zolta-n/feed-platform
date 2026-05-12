"""
Deduplication pipeline stage (EP3).

Pure function: dedup(raw_items, existing_url_hashes, existing_title_hashes,
                     recent_titles) -> list[Item]

Duplicate detection order:
  1. URL hash match against past 7 days
  2. Title hash match against past 7 days
  3. Fuzzy title similarity via difflib (threshold 0.85)

Duplicates are flagged is_duplicate=True; all items are returned so the
caller can batch-insert them; downstream stages filter on is_duplicate=0.
"""
from __future__ import annotations

import datetime
import difflib
import hashlib
import logging
import re
import uuid
from typing import Optional
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from ..models.types import Item, RawItem

logger = logging.getLogger(__name__)

FUZZY_THRESHOLD = 0.85
TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "ref", "source", "_ga",
})


def _normalize_url(url: str) -> str:
    """Strip tracking params, lowercase scheme/host, sort remaining params."""
    try:
        parsed = urlparse(url.strip())
        scheme = parsed.scheme.lower()
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/")
        qs = parse_qs(parsed.query, keep_blank_values=True)
        clean_qs = {k: v for k, v in qs.items() if k not in TRACKING_PARAMS}
        new_query = urlencode(sorted(clean_qs.items()), doseq=True)
        return urlunparse((scheme, netloc, path, "", new_query, ""))
    except Exception:
        return url.strip().lower()


def _url_hash(url: str) -> str:
    return hashlib.sha256(_normalize_url(url).encode()).hexdigest()


def _title_hash(title: str) -> str:
    normalized = re.sub(r"\s+", " ", title.strip().lower())
    return hashlib.sha256(normalized.encode()).hexdigest()


def _fuzzy_match(
    title: str,
    recent_titles: list[tuple[str, str]],
) -> Optional[str]:
    """Return item_id of the best fuzzy match above FUZZY_THRESHOLD, or None."""
    best_score = 0.0
    best_id: Optional[str] = None
    norm = re.sub(r"\s+", " ", title.strip().lower())
    for item_id, existing_title in recent_titles:
        existing_norm = re.sub(r"\s+", " ", existing_title.strip().lower())
        score = difflib.SequenceMatcher(None, norm, existing_norm).ratio()
        if score > best_score:
            best_score = score
            best_id = item_id
    if best_score >= FUZZY_THRESHOLD:
        return best_id
    return None


def dedup(
    raw_items: list[RawItem],
    feed_id: str,
    existing_url_hashes: set[str],
    existing_title_hashes: set[str],
    recent_titles: list[tuple[str, str]],
    run_id: Optional[str] = None,
) -> list[Item]:
    """Convert RawItems to Items, flagging duplicates.

    Args:
        raw_items: items from fetch stage
        feed_id: current feed identifier
        existing_url_hashes: url_hash values from items table (past 7 days)
        existing_title_hashes: title_hash values (past 7 days)
        recent_titles: list of (item_id, title) for fuzzy matching
        run_id: current pipeline run id

    Returns:
        list[Item] — all items; duplicates have is_duplicate=True
    """
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    items: list[Item] = []
    # Track hashes seen in this batch to catch intra-batch dupes
    batch_url_hashes: dict[str, str] = {}    # hash -> item_id
    batch_title_hashes: dict[str, str] = {}  # hash -> item_id
    batch_titles: list[tuple[str, str]] = []

    for raw in raw_items:
        uh = _url_hash(raw.url)
        th = _title_hash(raw.title) if raw.title else None

        is_dup = False
        dup_of: Optional[str] = None

        # 1. URL hash
        if uh in existing_url_hashes:
            is_dup = True
        elif uh in batch_url_hashes:
            is_dup = True
            dup_of = batch_url_hashes[uh]

        # 2. Title hash
        if not is_dup and th:
            if th in existing_title_hashes:
                is_dup = True
            elif th in batch_title_hashes:
                is_dup = True
                dup_of = batch_title_hashes[th]

        # 3. Fuzzy title match
        if not is_dup and raw.title:
            matched_id = _fuzzy_match(raw.title, recent_titles + batch_titles)
            if matched_id:
                is_dup = True
                dup_of = matched_id

        item_id = str(uuid.uuid4())
        pub_at = (
            raw.published_at.isoformat()
            if isinstance(raw.published_at, datetime.datetime)
            else raw.published_at
        )
        fetched_at = (
            raw.fetched_at.isoformat()
            if isinstance(raw.fetched_at, datetime.datetime)
            else now
        )

        item = Item(
            id=item_id,
            feed_id=feed_id,
            url=raw.url,
            url_hash=uh,
            title_hash=th,
            title=raw.title,
            body_raw=raw.body[:1000] if raw.body else None,
            source_id=raw.source_id,
            source_name=raw.extra.get("source_name", raw.source_id),
            source_language=raw.language,
            published_at=pub_at,
            fetched_at=fetched_at,
            run_id=run_id,
            is_duplicate=is_dup,
            duplicate_of=dup_of,
            region_tag=raw.extra.get("default_region"),
            topic_tag=raw.extra.get("default_topic"),
        )

        items.append(item)

        if not is_dup:
            batch_url_hashes[uh] = item_id
            existing_url_hashes.add(uh)
            if th:
                batch_title_hashes[th] = item_id
                existing_title_hashes.add(th)
            if raw.title:
                batch_titles.append((item_id, raw.title))

    dupes = sum(1 for i in items if i.is_duplicate)
    logger.info(
        "Dedup: %d raw items -> %d unique, %d duplicates",
        len(raw_items), len(raw_items) - dupes, dupes,
    )
    return items
