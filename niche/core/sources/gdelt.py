"""GDELT v2 Article Search API source adapter."""
from __future__ import annotations

import datetime
import logging
from typing import Optional

from ..models.types import RawItem

logger = logging.getLogger(__name__)

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False


class GDELTSource:
    """Fetches items from the GDELT v2 Article Search API.

    Query terms come from the FeedBundle taxonomy at runtime (EP1).
    """

    GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

    def __init__(
        self,
        source_id: str,
        name: str,
        query_terms: Optional[list[str]] = None,
        default_region: Optional[str] = None,
        default_topic: Optional[str] = None,
        max_records: int = 250,
        **kwargs,
    ) -> None:
        self.source_id = source_id
        self.name = name
        self.query_terms = query_terms or []
        self.default_region = default_region
        self.default_topic = default_topic
        self.max_records = max_records

    def fetch(self) -> list[RawItem]:
        if not _HAS_HTTPX or not self.query_terms:
            return []
        query = " OR ".join(f'"{t}"' for t in self.query_terms)
        params = {
            "query": query,
            "mode": "artlist",
            "maxrecords": self.max_records,
            "format": "json",
            "sourcelang": "english",
        }
        try:
            with httpx.Client(timeout=30) as client:
                resp = client.get(self.GDELT_URL, params=params)
                resp.raise_for_status()
                data = resp.json()
            articles = data.get("articles") or []
            now = datetime.datetime.now(datetime.timezone.utc)
            items = []
            for art in articles:
                url = art.get("url", "")
                if not url:
                    continue
                items.append(RawItem(
                    source_id=self.source_id,
                    url=url,
                    title=art.get("title", ""),
                    body=art.get("seendescription", "")[:1000],
                    language="en",
                    published_at=None,
                    fetched_at=now,
                    extra={"source_name": self.name,
                           "domain": art.get("domain"),
                           "default_region": self.default_region,
                           "default_topic": self.default_topic},
                ))
            logger.info("GDELT source %s: fetched %d items", self.source_id, len(items))
            return items
        except Exception as exc:
            logger.error("GDELT source %s fetch error: %s", self.source_id, exc)
            return []
