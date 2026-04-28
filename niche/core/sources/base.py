from typing import Protocol

from niche.core.models.types import RawItem


class Source(Protocol):
    source_id: str

    def fetch(self) -> list[RawItem]:
        """
        Pull items since the last successful fetch.
        Must not raise — return [] on any failure and log internally.
        Caller reads source_health for error details.
        """
        ...
