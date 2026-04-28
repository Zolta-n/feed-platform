from __future__ import annotations

from typing import Protocol

from niche.core.models.types import Item


class Translator(Protocol):
    def translate(self, item: Item) -> Item:
        ...
