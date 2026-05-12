"""
Source adapter base contract (EP2).

Every source type implements Source.fetch() -> list[RawItem].
Source is a Protocol (structural subtyping) — adapters don't need to
import or inherit from this module.
"""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

# Re-export from types so callers import from one place
from ..models.types import RawItem


@runtime_checkable
class Source(Protocol):
    source_id: str

    def fetch(self) -> list[RawItem]:
        """Pull items since the last successful fetch.

        Must not raise — return [] on any failure and log internally.
        Caller reads source_health for error details.
        """
        ...
