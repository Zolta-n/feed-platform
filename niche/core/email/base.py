from __future__ import annotations

from typing import Protocol


class EmailProvider(Protocol):
    def send(
        self,
        *,
        to: str,
        subject: str,
        html: str,
        from_email: str,
    ) -> None: ...
