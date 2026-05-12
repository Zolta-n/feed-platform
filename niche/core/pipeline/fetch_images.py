from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import replace
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from niche.core.models.types import Item

logger = logging.getLogger(__name__)

_USER_AGENT = "niche-feed-bot/1.0 (industry intelligence digest; +https://github.com/Zolta-n/feed-platform)"
_TIMEOUT_SECONDS = 5.0
_MAX_WORKERS = 10
_MAX_HTML_BYTES = 300_000  # only read the head/early body; og:image is always near the top


def fetch_og_images(items: list[Item]) -> list[Item]:
    """For items lacking image_url, fetch the article page and extract og:image.

    Pure function over the items list. HTTP failures, parse failures, or
    missing tags leave image_url=None and are logged but never raise.
    Items that already have image_url are passed through untouched.
    """
    needs_fetch = [(idx, item) for idx, item in enumerate(items) if not item.image_url]
    if not needs_fetch:
        return items

    fetched: dict[int, str] = {}

    with ThreadPoolExecutor(max_workers=_MAX_WORKERS) as pool:
        future_to_idx = {pool.submit(_fetch_one, item.url): idx for idx, item in needs_fetch}
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            try:
                image_url = future.result()
            except Exception as exc:
                logger.debug("og-image fetch failed for idx=%d: %s", idx, exc)
                continue
            if image_url:
                fetched[idx] = image_url

    if not fetched:
        logger.info("og-image: 0/%d items got an image", len(needs_fetch))
        return items

    logger.info(
        "og-image: %d/%d items got an image via fallback fetch",
        len(fetched), len(needs_fetch),
    )
    result = list(items)
    for idx, image_url in fetched.items():
        result[idx] = replace(result[idx], image_url=image_url)
    return result


def _fetch_one(url: str) -> str | None:
    """Fetch the page at url and return og:image (or twitter:image) if present."""
    headers = {"User-Agent": _USER_AGENT}
    try:
        with httpx.Client(timeout=_TIMEOUT_SECONDS, follow_redirects=True, headers=headers) as client:
            response = client.get(url)
            response.raise_for_status()
            html = response.text[:_MAX_HTML_BYTES]
            final_url = str(response.url)
    except Exception:
        return None
    return _extract_og_image(html, final_url)


def _extract_og_image(html: str, base_url: str) -> str | None:
    """Parse HTML for og:image (preferred) or twitter:image. Returns absolute URL or None."""
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return None

    for selector in [
        ("meta", {"property": "og:image"}),
        ("meta", {"property": "og:image:url"}),
        ("meta", {"name": "twitter:image"}),
        ("meta", {"name": "twitter:image:src"}),
    ]:
        tag = soup.find(selector[0], attrs=selector[1])
        if tag and tag.get("content"):
            return _absolutize(tag["content"].strip(), base_url)
    return None


def _absolutize(url: str, base_url: str) -> str | None:
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme in ("http", "https"):
        return url
    if not parsed.scheme:
        # protocol-relative or relative
        return urljoin(base_url, url)
    return None
