"""
Archive blueprint — searchable article archive.

Routes:
  GET /archive/   — search with optional query, date_from, date_to params
"""
from __future__ import annotations

import logging

from flask import Blueprint, current_app, render_template, request
from flask_login import current_user, login_required

logger = logging.getLogger(__name__)

archive_bp = Blueprint("archive", __name__, url_prefix="/archive")


def _repo():
    return current_app.config["REPO"]


def _bundle():
    return current_app.config.get("BUNDLE")


@archive_bp.route("/")
@login_required
def index():
    repo = _repo()
    bundle = _bundle()
    feed_id = bundle.config.feed_id if bundle else "default"

    query = request.args.get("q", "").strip()
    date_from = request.args.get("from", "").strip()
    date_to = request.args.get("to", "").strip()
    topic = request.args.get("topic", "").strip()
    page = max(1, int(request.args.get("page", 1)))
    per_page = 30

    with repo.connect() as conn:
        items = repo.search_items(
            conn, feed_id,
            query=query,
            limit=per_page,
            offset=(page - 1) * per_page,
            date_from=date_from or None,
            date_to=date_to or None,
        )

    # Filter by topic client-side if provided
    if topic:
        items = [i for i in items if i.topic_tag == topic]

    with repo.connect() as conn:
        feedback_map = repo.get_feedback_for_user(conn, current_user.id)
        saved_ids_list = repo.get_saved_item_ids(conn, current_user.id)

    prefs = None
    with repo.connect() as conn:
        prefs = repo.get_preferences(conn, current_user.id)
    theme_color = prefs.theme_color if prefs else "red"

    return render_template(
        "archive/index.html",
        items=items,
        query=query,
        date_from=date_from,
        date_to=date_to,
        topic=topic,
        page=page,
        feedback_map=feedback_map,
        saved_ids=set(saved_ids_list),
        theme_color=theme_color,
        bundle=bundle,
    )
