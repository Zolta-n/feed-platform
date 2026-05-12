"""Generic HTML press-room scraper source adapter."""
from __future__ import annotations

import datetime
import logging
import time
from typing import Optional
from urllib.parse import urljoin

from ..models.types import RawItem

logger = logging.getLogger(__name__)

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False

try:
    from bs4 import BeautifulSoup
    _HAS_BS4 = True
except ImportError:
    _HAS_BS4 = False

_USER_AGENT = "NicheFeedBot/1.0 (+https://github.com/niche-feed)"


class ScraperSource:
    """Scrapes a press-room page using CSS selectors from sources.yaml (EP1).

    Config fields (all in sources.yaml):
        url, item_selector, title_selector, link_selector,
        date_selector, body_selector
    """

    POLITENESS_DELAY = 2.0  # seconds between page requests

    def __init__(
        self,
        source_id: str,
        url: str,
        name: str,
        item_selector: str = "article",
        title_selector: str = "h2",
        link_selector: str = "a",
        date_selector: Optional[str] = None,
        body_selector: Optional[str] = None,
        default_region: Optional[str] = None,
        default_topic: Optional[str] = None,
        **kwargs,
    ) -> None:
        self.source_id = source_id
        self.url = url
        self.name = name
        self.item_selector = item_selector
        self.title_selector = title_selector
        self.link_selector = link_selector
        self.date_selector = date_selector
        self.body_selector = body_selector
        self.default_region = default_region
        self.default_topic = default_topic

    def fetch(self) -> list[RawItem]:
        if not _HAS_HTTPX or not _HAS_BS4:
            logger.warning(
                "ScraperSource %s: httpx or beautifulsoup4 not installed", self.source_id
            )
            return []
        try:
            with httpx.Client(
                timeout=30,
                headers={"User-Agent": _USER_AGENT},
                follow_redirects=True,
            ) as client:
                resp = client.get(self.url)
                resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            article_els = soup.select(self.item_selector)
            if not article_els:
                logger.warning(
                    "ScraperSource %s: selector '%s' matched 0 elements at %s",
                    self.source_id, self.item_selector, self.url,
                )
                return []
            now = datetime.datetime.now(datetime.timezone.utc)
            items = []
            for el in article_els:
                title_el = el.select_one(self.title_selector)
                link_el = el.select_one(self.link_selector)
                if not title_el or not link_el:
                    continue
                title = title_el.get_text(strip=True)
                href = link_el.get("href", "")
                if not href:
                    continue
                abs_url = href if href.startswith("http") else urljoin(self.url, href)
                date_str = None
                if self.date_selector:
                    date_el = el.select_one(self.date_selector)
                    if date_el:
                        date_str = date_el.get("datetime") or date_el.get_text(strip=True)
                body = ""
                if self.body_selector:
                    body_el = el.select_one(self.body_selector)
                    if body_el:
                        body = body_el.get_text(strip=True)[:1000]
                items.append(RawItem(
                    source_id=self.source_id,
                    url=abs_url,
                    title=title,
                    body=body,
                    language="en",
                    published_at=None,
                    fetched_at=now,
                    extra={
                        "source_name": self.name,
                        "date_str": date_str,
                        "default_region": self.default_region,
                        "default_topic": self.default_topic,
                    },
                ))
                time.sleep(self.POLITENESS_DELAY)
            logger.info(
                "ScraperSource %s: fetched %d items", self.source_id, len(items)
            )
            return items
        except Exception as exc:
            logger.error("ScraperSource %s fetch error: %s", self.source_id, exc)
            return []
