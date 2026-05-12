"""RSS/Atom source adapter using feedparser."""
from __future__ import annotations

import datetime
import logging
import re
import time
from typing import Optional

from ..models.types import RawItem

logger = logging.getLogger(__name__)

try:
    import feedparser
    _HAS_FEEDPARSER = True
except ImportError:
    _HAS_FEEDPARSER = False
    logger.warning("feedparser not installed; RSSSource will return []")


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _parse_date(entry) -> Optional[datetime.datetime]:
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        try:
            return datetime.datetime(*entry.published_parsed[:6],
                                     tzinfo=datetime.timezone.utc)
        except Exception:
            pass
    if hasattr(entry, "updated_parsed") and entry.updated_parsed:
        try:
            return datetime.datetime(*entry.updated_parsed[:6],
                                     tzinfo=datetime.timezone.utc)
        except Exception:
            pass
    return None


class RSSSource:
    """Fetches items from an RSS or Atom feed."""

    def __init__(
        self,
        source_id: str,
        url: str,
        name: str,
        default_region: Optional[str] = None,
        default_topic: Optional[str] = None,
        etag: Optional[str] = None,
        modified: Optional[str] = None,
        **kwargs,
    ) -> None:
        self.source_id = source_id
        self.url = url
        self.name = name
        self.default_region = default_region
        self.default_topic = default_topic
        self._etag = etag
        self._modified = modified

    def fetch(self) -> list[RawItem]:
        if not _HAS_FEEDPARSER:
            return []
        try:
            parsed = feedparser.parse(
                self.url,
                etag=self._etag,
                modified=self._modified,
            )
            if parsed.get("status") == 304:
                logger.info("RSS source %s: 304 Not Modified", self.source_id)
                return []
            if parsed.get("bozo") and not parsed.entries:
                logger.warning(
                    "RSS source %s bozo error: %s",
                    self.source_id,
                    parsed.get("bozo_exception"),
                )
                return []
            self._etag = parsed.get("etag")
            self._modified = parsed.get("modified")
            lang = (parsed.feed.get("language") or "en").split("-")[0].lower()
            now = datetime.datetime.now(datetime.timezone.utc)
            items = []
            for entry in parsed.entries:
                url = entry.get("link", "")
                if not url:
                    continue
                title = entry.get("title", "")
                body = _strip_html(
                    entry.get("summary", "")
                    or entry.get("content", [{}])[0].get("value", "")
                )[:1000]
                items.append(RawItem(
                    source_id=self.source_id,
                    url=url,
                    title=title,
                    body=body,
                    language=lang,
                    published_at=_parse_date(entry),
                    fetched_at=now,
                    extra={"source_name": self.name,
                           "default_region": self.default_region,
                           "default_topic": self.default_topic},
                ))
            logger.info("RSS source %s: fetched %d items", self.source_id, len(items))
            return items
        except Exception as exc:
            logger.error("RSS source %s fetch error: %s", self.source_id, exc)
            return []
