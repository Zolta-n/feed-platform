"""
Preferences blueprint — user preference wizard.

Routes:
  GET+POST /preferences/        — full preferences form
  POST     /preferences/theme   — quick theme color swap (AJAX)
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from flask import (
    Blueprint, abort, current_app, flash, jsonify, redirect,
    render_template, request, url_for,
)
from flask_login import current_user, login_required

from ...core.models.types import Preferences
from flask_wtf import FlaskForm


class PreferencesForm(FlaskForm):
    """Empty form just for CSRF token generation."""
    pass

logger = logging.getLogger(__name__)

preferences_bp = Blueprint("preferences", __name__, url_prefix="/preferences")


def _repo():
    return current_app.config["REPO"]


def _bundle():
    return current_app.config.get("BUNDLE")


def _feed_id() -> str:
    bundle = _bundle()
    return bundle.config.feed_id if bundle else "default"


@preferences_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    repo = _repo()
    bundle = _bundle()
    feed_id = _feed_id()

    with repo.connect() as conn:
        prefs = repo.get_preferences(conn, current_user.id)

    form = PreferencesForm()

    if form.validate_on_submit():
        # Parse submitted form values
        region_weights = {}
        topic_weights = {}
        company_boosts = {}
        keyword_boosts = []
        keyword_blocks = []
        theme_color = request.form.get("theme_color", "red")

        if bundle:
            for region in bundle.taxonomy.regions:
                val = request.form.get(f"region_{region.id}", "1.0")
                try:
                    region_weights[region.id] = float(val)
                except ValueError:
                    region_weights[region.id] = 1.0

            for topic in bundle.taxonomy.topics:
                val = request.form.get(f"topic_{topic.id}", "1.0")
                try:
                    topic_weights[topic.id] = float(val)
                except ValueError:
                    topic_weights[topic.id] = 1.0

        # Keyword boosts: comma-separated text input
        kb_raw = request.form.get("keyword_boosts", "")
        keyword_boosts_terms = [k.strip() for k in kb_raw.split(",") if k.strip()]
        keyword_boosts = [{"term": t, "weight": 1.5} for t in keyword_boosts_terms]

        # Keyword blocks: comma-separated
        kblocks_raw = request.form.get("keyword_blocks", "")
        keyword_blocks = [k.strip() for k in kblocks_raw.split(",") if k.strip()]

        # Email preferences
        user = current_user._core
        email_send_time = request.form.get("email_send_time", user.email_send_time)
        email_item_count = int(request.form.get("email_item_count", user.email_item_count))
        email_enabled = bool(request.form.get("email_enabled"))
        user.email_send_time = email_send_time
        user.email_item_count = email_item_count
        user.email_enabled = email_enabled
        with repo.connect() as conn:
            repo.update_user(conn, user)

        now = datetime.now(timezone.utc).isoformat()
        new_prefs = Preferences(
            id=prefs.id if prefs else str(uuid.uuid4()),
            user_id=current_user.id,
            feed_id=feed_id,
            region_weights=region_weights,
            topic_weights=topic_weights,
            company_boosts=company_boosts,
            keyword_boosts=keyword_boosts,
            keyword_blocks=keyword_blocks,
            updated_at=now,
            theme_color=theme_color,
        )
        with repo.connect() as conn:
            repo.upsert_preferences(conn, new_prefs)

        flash("Preferences saved.", "success")
        return redirect(url_for("preferences.index"))

    # Build display values for the template
    region_weights = (prefs.region_weights if prefs else {})
    topic_weights = (prefs.topic_weights if prefs else {})
    keyword_boosts_str = ", ".join(
        kb.get("term", "") for kb in (prefs.keyword_boosts if prefs else [])
    )
    keyword_blocks_str = ", ".join(prefs.keyword_blocks if prefs else [])

    return render_template(
        "preferences/index.html",
        form=form,
        prefs=prefs,
        taxonomy=bundle.taxonomy if bundle else None,
        region_weights=region_weights,
        topic_weights=topic_weights,
        keyword_boosts_str=keyword_boosts_str,
        keyword_blocks_str=keyword_blocks_str,
        theme_color=(prefs.theme_color if prefs else "red"),
    )


@preferences_bp.route("/theme", methods=["POST"])
@login_required
def update_theme():
    data = request.get_json(silent=True) or {}
    color = data.get("color", "red")
    valid_colors = {"red", "blue", "amber", "purple", "teal"}
    if color not in valid_colors:
        return jsonify({"error": "invalid color"}), 400

    repo = _repo()
    feed_id = _feed_id()
    with repo.connect() as conn:
        prefs = repo.get_preferences(conn, current_user.id)

    now = datetime.now(timezone.utc).isoformat()
    if prefs:
        prefs.theme_color = color
        prefs.updated_at = now
    else:
        prefs = Preferences(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            feed_id=feed_id,
            updated_at=now,
            theme_color=color,
        )

    with repo.connect() as conn:
        repo.upsert_preferences(conn, prefs)

    return jsonify({"ok": True, "color": color})
