"""Stub source for test-fixture — returns synthetic items without HTTP."""
from __future__ import annotations

import datetime
import uuid
from typing import Optional

from ..models.types import RawItem


class StubSource:
    """Returns synthetic RawItems. Used only in test-fixture (EP10)."""

    def __init__(
        self,
        source_id: str,
        name: str = "Stub Source",
        item_count: int = 3,
        default_region: Optional[str] = None,
        default_topic: Optional[str] = None,
        **kwargs,
    ) -> None:
        self.source_id = source_id
        self.name = name
        self.item_count = item_count
        self.default_region = default_region
        self.default_topic = default_topic

    def fetch(self) -> list[RawItem]:
        now = datetime.datetime.now(datetime.timezone.utc)
        return [
            RawItem(
                source_id=self.source_id,
                url=f"https://stub.example.com/item-{i}-{uuid.uuid4().hex[:8]}",
                title=f"Synthetic item {i} from {self.name}",
                body=f"This is synthetic body text for item {i}. "
                     f"AcmeBrake and FakeTier1Co are mentioned for test purposes.",
                language="en",
                published_at=now,
                fetched_at=now,
                extra={
                    "source_name": self.name,
                    "default_region": self.default_region,
                    "default_topic": self.default_topic,
                },
            )
            for i in range(self.item_count)
        ]
