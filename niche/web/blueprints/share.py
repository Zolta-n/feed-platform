"""
Share blueprint — public shareable item links and saved items list.

Routes:
  GET /share/<token>  — public item view (no auth, 7-day expiry)
  GET /share/saved    — authenticated user's saved items list
"""
from __future__ import annotations

import datetime
import logging

from flask import (
    Blueprint, abort, current_app, render_template,
)
from flask_login import current_user, login_required

logger = logging.getLogger(__name__)

share_bp = Blueprint("share", __name__, url_prefix="/share")


def _repo():
    return current_app.config["REPO"]


def _bundle():
    return current_app.config.get("BUNDLE")


def _feed_id() -> str:
    bundle = _bundle()
    return bundle.config.feed_id if bundle else "default"


@share_bp.route("/<token>")
def public_item(token: str):
    """Public item view — no authentication required; valid for 7 days."""
    repo = _repo()
    bundle = _bundle()

    with repo.connect() as conn:
        share = repo.get_share_token(conn, token)

    if not share:
        abort(404)

    # Check expiry
    expires_at = datetime.datetime.fromisoformat(
        share["expires_at"].replace("Z", "+00:00")
    )
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
    if datetime.datetime.now(datetime.timezone.utc) > expires_at:
        abort(410)  # Gone

    with repo.connect() as conn:
        item = repo.get_item(conn, share["item_id"])
    if not item:
        abort(404)

    return render_template(
        "share/public_item.html",
        item=item,
        bundle=bundle,
        expires_at=expires_at,
    )


@share_bp.route("/saved")
@login_required
def saved_items():
    repo = _repo()
    bundle = _bundle()
    feed_id = _feed_id()

    with repo.connect() as conn:
        saved_ids = repo.get_saved_item_ids(conn, current_user.id)
        items = repo.get_items_by_ids(conn, saved_ids)
        feedback_map = repo.get_feedback_for_user(conn, current_user.id)

    prefs = None
    with repo.connect() as conn:
        prefs = repo.get_preferences(conn, current_user.id)
    theme_color = prefs.theme_color if prefs else "red"

    return render_template(
        "share/saved.html",
        items=items,
        feedback_map=feedback_map,
        saved_ids=set(saved_ids),
        theme_color=theme_color,
        bundle=bundle,
    )
