from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Callable

import httpx

from niche.core.models.types import RawItem, SourceConfig
from niche.core.sources.retry import fetch_with_retry

logger = logging.getLogger(__name__)

_GDELT_DATE_FMT = "%Y%m%dT%H%M%SZ"


class GDELTSource:
    """GDELT v2 Document API source."""

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
        data = response.text
        import json
        payload = json.loads(data)
        articles = payload.get("articles") or []
        now = datetime.now(timezone.utc)
        items: list[RawItem] = []
        for article in articles:
            url = article.get("url", "")
            if not url:
                continue
            items.append(RawItem(
                source_id=self.source_id,
                url=url,
                title=article.get("title", "").strip(),
                body="",
                language=_parse_language(article.get("language", "")),
                published_at=_parse_date(article.get("seendate", "")),
                fetched_at=now,
            ))
        return items


def _parse_language(lang_str: str) -> str:
    mapping = {"English": "en", "German": "de", "French": "fr", "Japanese": "ja", "Chinese": "zh"}
    return mapping.get(lang_str, "en")


def _parse_date(date_str: str) -> datetime | None:
    if not date_str:
        return None
    try:
        return datetime.strptime(date_str, _GDELT_DATE_FMT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None
