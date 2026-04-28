from __future__ import annotations

import sqlite3


class User:
    """Flask-Login user backed by a sqlite3.Row from the users table."""

    def __init__(self, row: sqlite3.Row) -> None:
        self._row = row

    @property
    def id(self) -> str:
        return self._row["id"]

    @property
    def email(self) -> str:
        return self._row["email"]

    @property
    def is_admin(self) -> bool:
        return bool(self._row["is_admin"])

    @property
    def is_approved(self) -> bool:
        return bool(self._row["is_approved"])

    @property
    def feed_id(self) -> str:
        return self._row["feed_id"]

    # Flask-Login interface
    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_active(self) -> bool:
        return bool(self._row["is_approved"]) and self._row["deleted_at"] is None

    @property
    def is_anonymous(self) -> bool:
        return False

    def get_id(self) -> str:
        return self._row["id"]
