from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required

bp = Blueprint("api", __name__)


@bp.route("/feedback", methods=["POST"])
@login_required
def feedback():
    data = request.get_json(silent=True) or {}
    item_id = data.get("item_id", "")
    signal = data.get("signal", "")
    if not item_id or signal not in ("up", "down"):
        return jsonify({"error": "invalid"}), 400

    repo = current_app.config["REPO"]
    bundle = current_app.config["BUNDLE"]
    repo.insert_feedback(bundle.config.feed_id, current_user.id, item_id, signal)
    return jsonify({"ok": True})


@bp.route("/read", methods=["POST"])
@login_required
def mark_read():
    data = request.get_json(silent=True) or {}
    item_id = data.get("item_id", "")
    if not item_id:
        return jsonify({"error": "invalid"}), 400

    repo = current_app.config["REPO"]
    bundle = current_app.config["BUNDLE"]
    repo.mark_item_read(bundle.config.feed_id, current_user.id, item_id)
    return jsonify({"ok": True})


@bp.route("/export")
@login_required
def export_data():
    repo = current_app.config["REPO"]
    data = repo.export_user_data(current_user.id)
    return jsonify(data)


@bp.route("/save", methods=["POST"])
@login_required
def toggle_save():
    data = request.get_json(silent=True) or {}
    item_id = data.get("item_id", "")
    if not item_id:
        return jsonify({"error": "invalid"}), 400
    repo = current_app.config["REPO"]
    bundle = current_app.config["BUNDLE"]
    saved = repo.toggle_saved(current_user.id, item_id, bundle.config.feed_id)
    return jsonify({"saved": saved})


@bp.route("/share/<item_id>", methods=["POST"])
@login_required
def create_share(item_id: str):
    repo = current_app.config["REPO"]
    bundle = current_app.config["BUNDLE"]
    app_url = current_app.config.get("APP_URL", "http://localhost:5000")
    token = repo.create_share_token(item_id, bundle.config.feed_id)
    return jsonify({"url": f"{app_url}/share/{token}"})


@bp.route("/delete-account", methods=["POST"])
@login_required
def delete_account():
    from flask_login import logout_user
    repo = current_app.config["REPO"]
    repo.delete_user(current_user.id)
    logout_user()
    return jsonify({"ok": True})
