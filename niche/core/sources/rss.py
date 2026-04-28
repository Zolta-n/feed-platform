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
        response = httpx.get(self._config.url, timeout=30, follow_redirects=True)
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
            ))
        return items


def _parse_date(entry) -> datetime | None:
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            return datetime(*entry.published_parsed[:6], tzinfo=timezone.utc)
        except Exception:
            pass
    return None
