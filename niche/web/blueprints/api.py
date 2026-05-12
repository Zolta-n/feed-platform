"""
API blueprint — JSON endpoints for client-side interactions.

Routes:
  POST /api/feedback         — thumbs up/down signal
  POST /api/read             — mark item as read
  POST /api/save             — save/unsave item
  GET  /api/share/<item_id>  — generate shareable link
  POST /api/delete-account   — GDPR self-deletion
  GET  /api/export           — GDPR data export
"""
from __future__ import annotations

import datetime
import hashlib
import hmac
import logging
import secrets
import uuid

from flask import (
    Blueprint, abort, current_app, jsonify, request,
)
from flask_login import current_user, login_required

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__, url_prefix="/api")

SHARE_TOKEN_EXPIRY_DAYS = 7


def _repo():
    return current_app.config["REPO"]


def _bundle():
    return current_app.config.get("BUNDLE")


def _feed_id() -> str:
    bundle = _bundle()
    return bundle.config.feed_id if bundle else "default"


@api_bp.route("/feedback", methods=["POST"])
@login_required
def feedback():
    data = request.get_json(silent=True) or {}
    item_id = data.get("item_id") or request.form.get("item_id", "")
    signal = data.get("signal") or request.form.get("signal", "")

    if not item_id or signal not in ("up", "down"):
        return jsonify({"error": "item_id and signal (up/down) required"}), 400

    repo = _repo()
    feed_id = _feed_id()

    # Verify the item exists
    with repo.connect() as conn:
        item = repo.get_item(conn, item_id)
    if not item or item.feed_id != feed_id:
        return jsonify({"error": "item not found"}), 404

    with repo.connect() as conn:
        repo.upsert_feedback(conn, feed_id, current_user.id, item_id, signal)

    return jsonify({"ok": True, "signal": signal})


@api_bp.route("/read", methods=["POST"])
@login_required
def mark_read():
    data = request.get_json(silent=True) or {}
    item_id = data.get("item_id") or request.form.get("item_id", "")
    if not item_id:
        return jsonify({"error": "item_id required"}), 400

    repo = _repo()
    feed_id = _feed_id()
    with repo.connect() as conn:
        item = repo.get_item(conn, item_id)
    if not item or item.feed_id != feed_id:
        return jsonify({"error": "item not found"}), 404

    with repo.connect() as conn:
        repo.log_read(conn, feed_id, current_user.id, item_id, source="web")

    return jsonify({"ok": True})


@api_bp.route("/save", methods=["POST"])
@login_required
def save_item():
    data = request.get_json(silent=True) or {}
    item_id = data.get("item_id") or request.form.get("item_id", "")
    action = data.get("action", "save")  # "save" or "unsave"
    if not item_id:
        return jsonify({"error": "item_id required"}), 400

    repo = _repo()
    feed_id = _feed_id()
    with repo.connect() as conn:
        item = repo.get_item(conn, item_id)
    if not item or item.feed_id != feed_id:
        return jsonify({"error": "item not found"}), 404

    if action == "unsave":
        with repo.connect() as conn:
            removed = repo.unsave_item(conn, current_user.id, item_id)
        return jsonify({"ok": True, "saved": False})
    else:
        with repo.connect() as conn:
            newly_saved = repo.save_item(conn, feed_id, current_user.id, item_id)
        return jsonify({"ok": True, "saved": True})


@api_bp.route("/share/<item_id>")
@login_required
def share_item(item_id: str):
    repo = _repo()
    feed_id = _feed_id()
    with repo.connect() as conn:
        item = repo.get_item(conn, item_id)
    if not item or item.feed_id != feed_id:
        return jsonify({"error": "item not found"}), 404

    token = secrets.token_urlsafe(24)
    expires_at = (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(days=SHARE_TOKEN_EXPIRY_DAYS)
    ).isoformat()
    with repo.connect() as conn:
        repo.create_share_token(conn, token, item_id, feed_id, expires_at)

    app_url = current_app.config.get("APP_URL", "")
    share_url = f"{app_url}/share/{token}"
    return jsonify({"ok": True, "url": share_url})


@api_bp.route("/delete-account", methods=["POST"])
@login_required
def delete_account():
    repo = _repo()
    with repo.connect() as conn:
        repo.soft_delete_user(conn, current_user.id)
    from flask_login import logout_user
    logout_user()
    return jsonify({"ok": True, "message": "Account deleted."})


@api_bp.route("/export")
@login_required
def export_data():
    repo = _repo()
    with repo.connect() as conn:
        data = repo.export_user_data(conn, current_user.id)
    return jsonify(data)
