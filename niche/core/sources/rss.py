from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Callable

import feedparser
import httpx

from niche.core.models.types import RawItem, SourceConfig
from niche.core.sources.retry import fetch_with_retry

logger = logging.getLogger(__name__)

# Many publishers serve empty feeds or 403 to the default `python-httpx/...`
# User-Agent. A real browser UA is the reliable workaround. RSS feeds are
# public content meant to be aggregated; sites that genuinely care about
# identifying clients have other signals (Referer, API keys, etc.).
_FETCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/121.0.0.0 Safari/537.36"
    ),
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml; q=0.9, */*; q=0.8",
}


class RSSSource:
    def __init__(
        self,
        config: SourceConfig,
        repo,
        *,
        sleep_fn: Callable[[float], None] = time.sleep,
    ) -> None:
        self._config = config
        self._repo = repo
        self._sleep_fn = sleep_fn
        self.source_id = config.id

    def fetch(self) -> list[RawItem]:
        try:
            items = fetch_with_retry(
                self._do_fetch,
                self.source_id,
                sleep_fn=self._sleep_fn,
            )
            self._repo.update_source_health(
                self.source_id, self._config.feed_id, success=True, error_message=None
            )
            return items
        except Exception as exc:
            logger.error("source=%s all retries exhausted: %s", self.source_id, exc)
            self._repo.update_source_health(
                self.source_id, self._config.feed_id, success=False, error_message=str(exc)
            )
            return []

    def _do_fetch(self) -> list[RawItem]:
        response = httpx.get(
            self._config.url, timeout=30, follow_redirects=True, headers=_FETCH_HEADERS,
        )
        response.raise_for_status()
        feed = feedparser.parse(response.text)
        lang = (feed.feed.get("language") or "en")[:2]
        now = datetime.now(timezone.utc)
        items: list[RawItem] = []
        for entry in feed.entries:
            url = entry.get("link", "")
            if not url:
                continue
            items.append(RawItem(
                source_id=self.source_id,
                url=url,
                title=entry.get("title", "").strip(),
                body=entry.get("summary", ""),
                language=lang,
                published_at=_parse_date(entry),
                fetched_at=now,
                image_url=_extract_image(entry),
            ))
        return items


def _extract_image(entry) -> str | None:
    import re
    # media:content with image type
    for m in entry.get("media_content", []):
        url = m.get("url", "")
        if url and m.get("type", "").startswith("image"):
            return url
    # media:thumbnail
    for t in entry.get("media_thumbnail", []):
        url = t.get("url", "")
        if url:
            return url
    # enclosures
    for enc in entry.get("enclosures", []):
        if enc.get("type", "").startswith("image"):
            return enc.get("href") or enc.get("url", "")
    # links with image type
    for link in entry.get("links", []):
        if link.get("type", "").startswith("image"):
            return link.get("href", "")
    # <img> tags in summary or content HTML (common in WordPress feeds)
    _IMG_RE = re.compile(r'<img[^>]+src=["\']([^"\'>\s]+\.(jpg|jpeg|png|webp))', re.I)
    for html in [entry.get("summary", "")] + [c.get("value", "") for c in entry.get("content", [])]:
        m = _IMG_RE.search(html)
        if m:
            return m.group(1)
    return None


def _parse_date(entry) -> datetime | None:
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        except Exception:
            pass
    return None
