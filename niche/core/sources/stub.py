from datetime import datetime, timezone

from niche.core.models.types import RawItem


class StubSource:
    """Synthetic source for M1 and testing. Returns fixed items; no network calls."""

    def __init__(self, source_id: str, feed_id: str) -> None:
        self.source_id = source_id
        self._feed_id = feed_id

    def fetch(self) -> list[RawItem]:
        now = datetime.now(timezone.utc)
        return [
            RawItem(
                source_id=self.source_id,
                url=f"https://stub.invalid/item/{i}",
                title=f"Stub Item {i}: synthetic test content",
                body=f"This is stub body content for item {i}. It contains synthetic text.",
                language="en",
                published_at=now,
                fetched_at=now,
            )
            for i in range(1, 6)
        ]
