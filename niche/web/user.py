"""Flask-Login UserMixin wrapper around the core User dataclass."""
from __future__ import annotations

from flask_login import UserMixin

from ..core.models.types import User as CoreUser


class LoginUser(UserMixin):
    """Thin wrapper that adapts CoreUser to Flask-Login's interface."""

    def __init__(self, core_user: CoreUser) -> None:
        self._user = core_user

    # Flask-Login required interface
    def get_id(self) -> str:
        return self._user.id

    @property
    def is_active(self) -> bool:
        return self._user.is_approved and self._user.deleted_at is None

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def is_anonymous(self) -> bool:
        return False

    # Pass-through to core user fields
    @property
    def id(self) -> str:
        return self._user.id

    @property
    def email(self) -> str:
        return self._user.email

    @property
    def feed_id(self) -> str:
        return self._user.feed_id

    @property
    def is_admin(self) -> bool:
        return self._user.is_admin

    @property
    def is_approved(self) -> bool:
        return self._user.is_approved

    @property
    def ui_language(self) -> str:
        return self._user.ui_language

    @property
    def email_enabled(self) -> bool:
        return self._user.email_enabled

    @property
    def email_send_time(self) -> str:
        return self._user.email_send_time

    @property
    def email_item_count(self) -> int:
        return self._user.email_item_count

    @property
    def deleted_at(self):
        return self._user.deleted_at

    @property
    def theme_color(self) -> str:
        """Returns the user's preferred theme color.
        Loaded from preferences by the before_request hook in app.py."""
        return getattr(self, "_theme_color", "red")

    @theme_color.setter
    def theme_color(self, value: str):
        self._theme_color = value

    @property
    def _core(self) -> CoreUser:
        return self._user
