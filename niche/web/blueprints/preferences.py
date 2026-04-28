from __future__ import annotations

import json

from flask import Blueprint, current_app, redirect, render_template, request, url_for
from flask_login import current_user, login_required

bp = Blueprint("preferences", __name__)

_VALID_THEME_COLORS = {"red", "blue", "amber", "purple", "teal"}


@bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    repo = current_app.config["REPO"]
    bundle = current_app.config["BUNDLE"]

    prefs_row = repo.get_user_preferences(current_user.id)
    prefs = {}
    theme_color = "red"
    if prefs_row:
        prefs = {
            "topic_weights": json.loads(prefs_row["topic_weights"] or "{}"),
            "region_weights": json.loads(prefs_row["region_weights"] or "{}"),
            "company_boosts": json.loads(prefs_row["company_boosts"] or "{}"),
            "keyword_blocks": json.loads(prefs_row["keyword_blocks"] or "[]"),
            "keyword_boosts": json.loads(prefs_row["keyword_boosts"] or "[]"),
        }
        try:
            theme_color = prefs_row["theme_color"] or "red"
        except (KeyError, IndexError):
            theme_color = "red"

    if request.method == "POST":
        topic_weights = {}
        for topic in bundle.taxonomy.topics:
            val = request.form.get(f"topic_{topic.id}", "1.0")
            try:
                topic_weights[topic.id] = float(val)
            except ValueError:
                topic_weights[topic.id] = 1.0

        region_weights = {}
        for region in bundle.taxonomy.regions:
            val = request.form.get(f"region_{region.id}", "1.0")
            try:
                region_weights[region.id] = float(val)
            except ValueError:
                region_weights[region.id] = 1.0

        raw_blocks = request.form.get("keyword_blocks", "")
        keyword_blocks = [w.strip() for w in raw_blocks.split(",") if w.strip()]

        raw_boosts = request.form.get("keyword_boosts", "")
        keyword_boosts = [w.strip() for w in raw_boosts.split(",") if w.strip()]

        submitted_theme = request.form.get("theme_color", "red")
        new_theme_color = submitted_theme if submitted_theme in _VALID_THEME_COLORS else "red"

        new_prefs = {
            "topic_weights": topic_weights,
            "region_weights": region_weights,
            "company_boosts": {},
            "keyword_blocks": keyword_blocks,
            "keyword_boosts": keyword_boosts,
            "theme_color": new_theme_color,
        }
        repo.save_user_preferences(current_user.id, bundle.config.feed_id, new_prefs)
        return redirect(url_for("preferences.index"))

    return render_template(
        "preferences/index.html",
        topics=bundle.taxonomy.topics,
        regions=bundle.taxonomy.regions,
        prefs=prefs,
        theme_color=theme_color,
    )
