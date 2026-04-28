from __future__ import annotations

from functools import wraps

from flask import Blueprint, abort, current_app, render_template, request, redirect, url_for
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


@bp.route("/costs")
@admin_required
def costs():
    repo = current_app.config["REPO"]
    bundle = current_app.config["BUNDLE"]
    days = int(request.args.get("days", 30))
    summary = repo.get_llm_costs_summary(bundle.config.feed_id, days=days)
    total_usd = sum(r["usd"] for r in summary)
    return render_template("admin/costs.html", summary=summary, total_usd=total_usd, days=days)
