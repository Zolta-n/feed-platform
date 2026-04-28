from __future__ import annotations

from flask import Blueprint, current_app, render_template, request
from flask_login import login_required

bp = Blueprint("archive", __name__)


@bp.route("/")
@login_required
def index():
    repo = current_app.config["REPO"]
    bundle = current_app.config["BUNDLE"]

    keyword = request.args.get("q", "").strip() or None
    date_from = request.args.get("from", "").strip() or None
    date_to = request.args.get("to", "").strip() or None

    items = repo.get_archive_items(
        bundle.config.feed_id,
        keyword=keyword,
        date_from=date_from,
        date_to=date_to,
        limit=50,
    )

    return render_template(
        "archive/index.html",
        items=items,
        keyword=keyword or "",
        date_from=date_from or "",
        date_to=date_to or "",
    )
