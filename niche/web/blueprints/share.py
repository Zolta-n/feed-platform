from __future__ import annotations
from flask import Blueprint, current_app, render_template, abort
from flask_login import current_user, login_required
from datetime import datetime, timezone

bp = Blueprint("share", __name__)


@bp.route("/saved")
@login_required
def saved():
    repo = current_app.config["REPO"]
    bundle = current_app.config["BUNDLE"]
    items = repo.get_saved_items(current_user.id, bundle.config.feed_id)
    return render_template("share/saved.html", items=items)


@bp.route("/share/<token>")
def public_item(token: str):
    repo = current_app.config["REPO"]
    row = repo.get_share_token(token)
    if not row:
        abort(404)
    if row["expires_at"] < datetime.now(timezone.utc).isoformat():
        abort(410)
    item = repo.get_item_by_id(row["item_id"])
    if not item:
        abort(404)
    bundle = current_app.config["BUNDLE"]
    return render_template("share/public_item.html", item=item, bundle=bundle)
