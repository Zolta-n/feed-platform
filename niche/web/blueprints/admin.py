"""
Admin blueprint — dashboard, sources, users, costs, watchlist, pipeline trigger.

All routes require login_required + is_admin check.

Routes:
  GET+POST /admin/         — dashboard + pipeline status
  GET      /admin/costs    — LLM cost log
  POST     /admin/run      — manual pipeline trigger
  GET      /admin/run-status/<run_id> — live run status (JSON)
  POST     /admin/schedule — update pipeline schedule
  POST     /admin/send-digest — trigger email digest send
  GET      /admin/sources  — source health table
  GET      /admin/users    — user list + approval queue
  POST     /admin/users/approve/<user_id> — approve user
  POST     /admin/users/delete/<user_id>  — delete user
  GET      /admin/watchlist — watchlist management
  POST     /admin/watchlist/add — add watchlist entry
  POST     /admin/watchlist/<entry_id>/edit — edit entry
  POST     /admin/watchlist/<entry_id>/delete — delete entry
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from functools import wraps

from flask import (
    Blueprint, abort, current_app, flash, jsonify, redirect,
    render_template, request, url_for,
)
from flask_login import current_user, login_required

logger = logging.getLogger(__name__)

admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _repo():
    return current_app.config["REPO"]


def _bundle():
    return current_app.config.get("BUNDLE")


def admin_required(f):
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _feed_id() -> str:
    bundle = _bundle()
    return bundle.config.feed_id if bundle else "default"


@admin_bp.route("/", methods=["GET", "POST"])
@admin_required
def index():
    repo = _repo()
    bundle = _bundle()
    feed_id = _feed_id()
    from datetime import date
    year_month = date.today().strftime("%Y-%m")

    with repo.connect() as conn:
        recent_runs = repo.get_recent_pipeline_runs(conn, feed_id, limit=7)
        all_users = repo.get_all_users(conn, feed_id)
        all_sources = repo.get_sources(conn, feed_id, enabled_only=False)
        health_rows = repo.get_source_health(conn, feed_id)
        # Item count
        row = conn.execute("SELECT COUNT(*) AS c FROM items WHERE feed_id=?", (feed_id,)).fetchone()
        item_count = row["c"] if row else 0
        month_cost = repo.get_cost_for_month(conn, feed_id, year_month)

    latest_run = recent_runs[0] if recent_runs else None
    user_count = len([u for u in all_users if not u.deleted_at])
    pending_count = len([u for u in all_users if not u.is_approved and not u.deleted_at])
    source_count = len(all_sources)
    unhealthy_count = len([h for h in health_rows if h.get("is_flagged")])

    scheduler = current_app.config.get("SCHEDULER")
    scheduler_running = scheduler is not None and scheduler.running if scheduler else False
    next_run = None
    scheduler_run_time = bundle.config.daily_run_time if bundle else "05:00"
    scheduler_timezone = bundle.config.timezone if bundle else "UTC"
    if scheduler and scheduler_running:
        try:
            job = scheduler.get_job("daily_pipeline")
            if job and job.next_run_time:
                next_run = job.next_run_time.strftime("%Y-%m-%d %H:%M %Z")
        except Exception:
            pass

    return render_template(
        "admin/index.html",
        recent_runs=recent_runs,
        latest_run=latest_run,
        user_count=user_count,
        pending_count=pending_count,
        source_count=source_count,
        unhealthy_count=unhealthy_count,
        item_count=item_count,
        month_cost=month_cost,
        scheduler_running=scheduler_running,
        scheduler_run_time=scheduler_run_time,
        scheduler_timezone=scheduler_timezone,
        next_run=next_run,
        bundle=bundle,
    )


@admin_bp.route("/costs")
@admin_required
def costs():
    repo = _repo()
    bundle = _bundle()
    feed_id = _feed_id()

    from datetime import date
    year_month = date.today().strftime("%Y-%m")
    with repo.connect() as conn:
        cost_entries = repo.get_cost_log(conn, feed_id, limit=200)
        monthly_total = repo.get_cost_for_month(conn, feed_id, year_month)

    # Group by date
    by_date: dict[str, list] = {}
    for entry in cost_entries:
        day = entry["called_at"][:10] if entry.get("called_at") else "unknown"
        by_date.setdefault(day, []).append(entry)

    return render_template(
        "admin/costs.html",
        cost_entries=cost_entries,
        monthly_total=monthly_total,
        monthly_cap=float(os.environ.get("MONTHLY_COST_CAP_USD", "18.00")),
        year_month=year_month,
        by_date=by_date,
        bundle=bundle,
    )


@admin_bp.route("/run", methods=["POST"])
@admin_required
def run_pipeline():
    """Manually trigger a pipeline run in a subprocess."""
    python = current_app.config.get("PYTHON_EXECUTABLE") or sys.executable
    feed_dir = current_app.config.get("FEED_DIR", "feeds/brake-by-wire")
    db_path = current_app.config.get("DB_PATH", "niche.db")
    run_id = str(uuid.uuid4())

    env = os.environ.copy()
    pythonpath = current_app.config.get("PYTHONPATH", "")
    if pythonpath:
        env["PYTHONPATH"] = pythonpath

    try:
        subprocess.Popen(
            [python, "cli.py", "pipeline", "run",
             "--feed-dir", feed_dir, "--db-path", db_path,
             "--run-id", run_id],
            env=env,
        )
        flash(f"Pipeline run started (run_id: {run_id})", "success")
    except Exception as exc:
        logger.error("Failed to start pipeline subprocess: %s", exc)
        flash(f"Failed to start pipeline: {exc}", "error")

    return redirect(url_for("admin.index"))


@admin_bp.route("/run-status/<run_id>")
@admin_required
def run_status(run_id: str):
    repo = _repo()
    with repo.connect() as conn:
        run = repo.get_pipeline_run(conn, run_id)
    if not run:
        return jsonify({"error": "not found"}), 404
    return jsonify(run)


@admin_bp.route("/schedule", methods=["POST"])
@admin_required
def set_schedule():
    run_time = request.form.get("run_time", "05:00").strip()
    tz_name = request.form.get("timezone", "UTC").strip()
    # Update scheduler if running
    scheduler = current_app.config.get("SCHEDULER")
    if scheduler and scheduler.running:
        try:
            hour, minute = (int(x) for x in run_time.split(":"))
            scheduler.reschedule_job(
                "daily_pipeline",
                trigger="cron",
                hour=hour,
                minute=minute,
                timezone=tz_name,
            )
            flash(f"Schedule updated to {run_time} ({tz_name}).", "success")
        except Exception as exc:
            flash(f"Failed to update schedule: {exc}", "error")
    else:
        flash("Scheduler not running.", "info")
    return redirect(url_for("admin.index"))


@admin_bp.route("/send-digest", methods=["POST"])
@admin_required
def send_digest():
    python = current_app.config.get("PYTHON_EXECUTABLE") or sys.executable
    feed_dir = current_app.config.get("FEED_DIR", "feeds/brake-by-wire")
    db_path = current_app.config.get("DB_PATH", "niche.db")
    env = os.environ.copy()
    pythonpath = current_app.config.get("PYTHONPATH", "")
    if pythonpath:
        env["PYTHONPATH"] = pythonpath
    try:
        subprocess.Popen(
            [python, "cli.py", "agent", "send",
             "--feed-dir", feed_dir, "--db-path", db_path],
            env=env,
        )
        flash("Digest email send triggered.", "success")
    except Exception as exc:
        flash(f"Failed to trigger send: {exc}", "error")
    return redirect(url_for("admin.index"))


@admin_bp.route("/sources")
@admin_required
def sources():
    repo = _repo()
    bundle = _bundle()
    feed_id = _feed_id()

    with repo.connect() as conn:
        all_sources = repo.get_sources(conn, feed_id, enabled_only=False)
        health_rows = repo.get_source_health(conn, feed_id)

    health_by_id = {h["source_id"]: h for h in health_rows}

    return render_template(
        "admin/sources.html",
        sources=all_sources,
        health_by_id=health_by_id,
        bundle=bundle,
    )


@admin_bp.route("/users")
@admin_required
def users():
    repo = _repo()
    bundle = _bundle()
    feed_id = _feed_id()

    with repo.connect() as conn:
        all_users = repo.get_all_users(conn, feed_id)

    pending = [u for u in all_users if not u.is_approved and not u.deleted_at]
    approved = [u for u in all_users if u.is_approved and not u.deleted_at]

    return render_template(
        "admin/users.html",
        pending=pending,
        approved=approved,
        bundle=bundle,
    )


@admin_bp.route("/users/approve/<user_id>", methods=["POST"])
@admin_required
def approve_user(user_id: str):
    repo = _repo()
    bundle = _bundle()
    feed_id = _feed_id()

    with repo.connect() as conn:
        user = repo.get_user(conn, user_id)
    if not user or user.feed_id != feed_id:
        abort(404)

    user.is_approved = True
    with repo.connect() as conn:
        repo.update_user(conn, user)

    # Send welcome magic link
    import datetime
    from ..auth.magic_link import generate_magic_token
    token = generate_magic_token()
    expires_at = (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(minutes=15)
    ).isoformat()
    with repo.connect() as conn:
        repo.create_magic_token(conn, token, user.email, expires_at)

    from .auth import _send_magic_link
    _send_magic_link(user.email, token)
    flash(f"User {user.email} approved and login link sent.", "success")
    return redirect(url_for("admin.users"))


# Alias for template that calls admin.approve_user with user_id kwarg


@admin_bp.route("/users/delete/<user_id>", methods=["POST"])
@admin_required
def delete_user(user_id: str):
    repo = _repo()
    feed_id = _feed_id()
    with repo.connect() as conn:
        user = repo.get_user(conn, user_id)
    if not user or user.feed_id != feed_id:
        abort(404)
    with repo.connect() as conn:
        repo.soft_delete_user(conn, user_id)
    flash(f"User {user.email} deleted.", "success")
    return redirect(url_for("admin.users"))


@admin_bp.route("/watchlist")
@admin_required
def watchlist():
    repo = _repo()
    bundle = _bundle()
    feed_id = _feed_id()

    with repo.connect() as conn:
        entries = repo.get_watchlist(conn, feed_id)

    return render_template(
        "admin/watchlist.html",
        entries=entries,
        bundle=bundle,
    )


@admin_bp.route("/watchlist/add", methods=["POST"])
@admin_required
def watchlist_add():
    repo = _repo()
    feed_id = _feed_id()
    name = request.form.get("name", "").strip()
    if not name:
        flash("Name is required.", "error")
        return redirect(url_for("admin.watchlist"))
    entry_id = request.form.get("id", "").strip() or name.lower().replace(" ", "-")
    aliases_raw = request.form.get("aliases", "")
    aliases = [a.strip() for a in aliases_raw.split(",") if a.strip()]
    boost = float(request.form.get("boost", 1.5))
    role = request.form.get("role", "").strip() or None
    notes = request.form.get("notes", "").strip() or None
    entry_type = request.form.get("entry_type", "company")

    with repo.connect() as conn:
        repo.upsert_watchlist_entry(
            conn, entry_id, feed_id, entry_type, name, aliases, boost, role, notes
        )
    flash(f"Watchlist entry '{name}' added.", "success")
    return redirect(url_for("admin.watchlist"))


@admin_bp.route("/watchlist/<entry_id>/edit", methods=["POST"])
@admin_required
def watchlist_edit(entry_id: str):
    repo = _repo()
    feed_id = _feed_id()
    name = request.form.get("name", "").strip()
    aliases_raw = request.form.get("aliases", "")
    aliases = [a.strip() for a in aliases_raw.split(",") if a.strip()]
    boost = float(request.form.get("boost", 1.5))
    role = request.form.get("role", "").strip() or None
    notes = request.form.get("notes", "").strip() or None
    enabled = request.form.get("enabled", "1") == "1"
    entry_type = request.form.get("entry_type", "company")

    with repo.connect() as conn:
        repo.upsert_watchlist_entry(
            conn, entry_id, feed_id, entry_type, name, aliases, boost, role, notes, enabled
        )
    flash(f"Watchlist entry updated.", "success")
    return redirect(url_for("admin.watchlist"))


@admin_bp.route("/watchlist/<entry_id>/delete", methods=["POST"])
@admin_required
def watchlist_delete(entry_id: str):
    repo = _repo()
    feed_id = _feed_id()
    with repo.connect() as conn:
        repo.delete_watchlist_entry(conn, entry_id, feed_id)
    flash("Watchlist entry deleted.", "success")
    return redirect(url_for("admin.watchlist"))
