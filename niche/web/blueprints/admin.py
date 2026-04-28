from __future__ import annotations

import threading
import uuid
from functools import wraps

from flask import Blueprint, abort, current_app, flash, render_template, request, redirect, url_for
from flask_login import current_user, login_required

bp = Blueprint("admin", __name__)


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


@bp.route("/")
@admin_required
def index():
    repo = current_app.config["REPO"]
    bundle = current_app.config["BUNDLE"]
    runs = repo.get_pipeline_runs(bundle.config.feed_id, limit=10)
    return render_template("admin/index.html", runs=runs)


@bp.route("/sources")
@admin_required
def sources():
    repo = current_app.config["REPO"]
    bundle = current_app.config["BUNDLE"]
    health = repo.get_all_source_health(bundle.config.feed_id)
    return render_template("admin/sources.html", sources=health)


@bp.route("/users")
@admin_required
def users():
    repo = current_app.config["REPO"]
    bundle = current_app.config["BUNDLE"]
    all_users = repo.get_all_users(bundle.config.feed_id)
    return render_template("admin/users.html", users=all_users)


@bp.route("/users/approve/<user_id>", methods=["POST"])
@admin_required
def approve_user(user_id: str):
    repo = current_app.config["REPO"]
    repo.approve_user(user_id)
    return redirect(url_for("admin.users"))


@bp.route("/users/delete/<user_id>", methods=["POST"])
@admin_required
def delete_user(user_id: str):
    repo = current_app.config["REPO"]
    repo.delete_user(user_id)
    return redirect(url_for("admin.users"))


@bp.route("/run", methods=["POST"])
@admin_required
def run_pipeline():
    from niche.core.pipeline.runner import run_pipeline as _run

    app = current_app._get_current_object()
    repo = app.config["REPO"]
    bundle = app.config["BUNDLE"]
    run_id = uuid.uuid4().hex

    def _worker():
        with app.app_context():
            try:
                _run(bundle, repo, run_id)
            except Exception:
                pass

    threading.Thread(target=_worker, daemon=True).start()
    flash(f"Pipeline run {run_id[:8]}… started in background.", "info")
    return redirect(url_for("admin.index"))


@bp.route("/send-digest", methods=["POST"])
@admin_required
def send_digest():
    from niche.core.email.digest_sender import send_digest as _send

    app = current_app._get_current_object()
    repo = app.config["REPO"]
    bundle = app.config["BUNDLE"]
    email_provider = app.config.get("EMAIL_PROVIDER")
    app_url = app.config.get("APP_URL", "http://localhost:5000")

    if not email_provider:
        flash("No email provider configured.", "error")
        return redirect(url_for("admin.index"))

    sent = _send(bundle, repo, email_provider, app_url)
    flash(f"Digest sent to {sent} subscriber(s).", "info")
    return redirect(url_for("admin.index"))


@bp.route("/costs")
@admin_required
def costs():
    repo = current_app.config["REPO"]
    bundle = current_app.config["BUNDLE"]
    days = int(request.args.get("days", 30))
    summary = repo.get_llm_costs_summary(bundle.config.feed_id, days=days)
    total_usd = sum(r["usd"] for r in summary)
    return render_template("admin/costs.html", summary=summary, total_usd=total_usd, days=days)
