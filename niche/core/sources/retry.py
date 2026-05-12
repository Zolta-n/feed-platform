"""Retry wrapper for source adapters.

Adds 3-attempt exponential-backoff retry around any Source.fetch() call.
"""
from __future__ import annotations

import logging
import time
from typing import Callable

from ..models.types import RawItem

logger = logging.getLogger(__name__)


def fetch_with_retry(
    source_id: str,
    fetch_fn: Callable[[], list[RawItem]],
    max_attempts: int = 3,
    base_delay: float = 5.0,
) -> list[RawItem]:
    """Call fetch_fn up to max_attempts times with exponential backoff.

    Returns [] if all attempts fail.  Never raises.
    """
    last_exc: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            items = fetch_fn()
            if attempt > 1:
                logger.info(
                    "Source %s succeeded on attempt %d", source_id, attempt
                )
            return items
        except Exception as exc:
            last_exc = exc
            delay = base_delay * (2 ** (attempt - 1))
            logger.warning(
                "Source %s attempt %d/%d failed: %s. Retrying in %.0fs",
                source_id, attempt, max_attempts, exc, delay,
            )
            if attempt < max_attempts:
                time.sleep(delay)
    logger.error(
        "Source %s: all %d attempts failed. Last error: %s",
        source_id, max_attempts, last_exc,
    )
    return []
