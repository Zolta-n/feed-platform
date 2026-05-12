"""Google News RSS source adapter."""
from __future__ import annotations

import datetime
import logging
import re
import urllib.parse
from typing import Optional

from ..models.types import RawItem

logger = logging.getLogger(__name__)

try:
    import feedparser
    _HAS_FEEDPARSER = True
except ImportError:
    _HAS_FEEDPARSER = False


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", "", text or "").strip()


class GoogleNewsSource:
    """Fetches items from Google News RSS search for configured query terms (EP1)."""

    BASE_URL = "https://news.google.com/rss/search"

    def __init__(
        self,
        source_id: str,
        name: str,
        query_terms: Optional[list[str]] = None,
        language: str = "en",
        country: str = "US",
        default_region: Optional[str] = None,
        default_topic: Optional[str] = None,
        **kwargs,
    ) -> None:
        self.source_id = source_id
        self.name = name
        self.query_terms = query_terms or []
        self.language = language
        self.country = country
        self.default_region = default_region
        self.default_topic = default_topic

    def _build_url(self, term: str) -> str:
        params = {
            "q": term,
            "hl": self.language,
            "gl": self.country,
            "ceid": f"{self.country}:{self.language}",
        }
        return self.BASE_URL + "?" + urllib.parse.urlencode(params)

    def fetch(self) -> list[RawItem]:
        if not _HAS_FEEDPARSER or not self.query_terms:
            return []
        now = datetime.datetime.now(datetime.timezone.utc)
        items = []
        seen_urls: set[str] = set()
        for term in self.query_terms:
            url = self._build_url(term)
            try:
                parsed = feedparser.parse(url)
                if parsed.get("bozo") and not parsed.entries:
                    logger.warning(
                        "GoogleNews source %s bozo: %s",
                        self.source_id,
                        parsed.get("bozo_exception"),
                    )
                    continue
                for entry in parsed.entries:
                    link = entry.get("link", "")
                    if not link or link in seen_urls:
                        continue
                    seen_urls.add(link)
                    pub_parsed = getattr(entry, "published_parsed", None)
                    published_at = None
                    if pub_parsed:
                        try:
                            published_at = datetime.datetime(
                                *pub_parsed[:6], tzinfo=datetime.timezone.utc
                            )
                        except Exception:
                            pass
                    items.append(RawItem(
                        source_id=self.source_id,
                        url=link,
                        title=entry.get("title", ""),
                        body=_strip_html(entry.get("summary", ""))[:1000],
                        language=self.language,
                        published_at=published_at,
                        fetched_at=now,
                        extra={"source_name": self.name,
                               "query_term": term,
                               "default_region": self.default_region,
                               "default_topic": self.default_topic},
                    ))
            except Exception as exc:
                logger.error(
                    "GoogleNews source %s term '%s' error: %s",
                    self.source_id, term, exc,
                )
        logger.info("GoogleNews source %s: fetched %d items", self.source_id, len(items))
        return items
