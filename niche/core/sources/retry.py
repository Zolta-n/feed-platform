from __future__ import annotations

import logging
import time
from typing import Callable

from niche.core.models.types import RawItem

logger = logging.getLogger(__name__)


def fetch_with_retry(
    fn: Callable[[], list[RawItem]],
    source_id: str,
    *,
    attempts: int = 3,
    backoff_s: float = 5.0,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> list[RawItem]:
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            logger.warning(
                "source=%s fetch attempt %d/%d failed: %s",
                source_id, attempt, attempts, exc,
            )
            if attempt < attempts:
                sleep_fn(backoff_s * (2 ** (attempt - 1)))
    raise last_exc  # type: ignore[misc]
