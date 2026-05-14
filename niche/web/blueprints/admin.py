from __future__ import annotations

import uuid
from functools import wraps

from flask import Blueprint, abort, current_app, flash, jsonify, render_template, request, redirect, url_for
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
    import subprocess, sys, os

    app = current_app._get_current_object()
    bundle = app.config["BUNDLE"]
    db_path = app.config.get("DB_PATH")
    feed_dir = app.config.get("FEED_DIR") or bundle.feed_dir
    run_id = uuid.uuid4().hex

    # Use the Python captured at WSGI startup — guaranteed to be the virtualenv Python.
    python = app.config.get("PYTHON_EXECUTABLE") or sys.executable

    cli_path = os.path.join(os.path.dirname(os.path.dirname(app.root_path)), "cli.py")
    cmd = [
        python,
        cli_path,
        "pipeline", "run",
        "--feed-dir", feed_dir,
        "--run-id", run_id,
    ]
    if db_path:
        cmd += ["--db-path", db_path]

    import os as _os
    env = _os.environ.copy()
    env["PYTHONPATH"] = _os.path.dirname(_os.path.dirname(app.root_path))

    log_path = _os.path.join(_os.path.dirname(_os.path.dirname(app.root_path)), "pipeline_subprocess.log")
    try:
        with open(log_path, "a") as log_f:
            subprocess.Popen(cmd, close_fds=True, env=env, stdout=log_f, stderr=log_f)
    except Exception as exc:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify({"error": str(exc)}), 500
        flash(f"Could not start pipeline: {exc}", "error")
        return redirect(url_for("admin.index"))

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return jsonify({"run_id": run_id})

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


@bp.route("/run-status/<run_id>")
@admin_required
def run_status(run_id: str):
    repo = current_app.config["REPO"]
    run = repo.get_pipeline_run(run_id)
    if not run:
        return jsonify({"error": "not found"}), 404
    return jsonify({
        "status":            run["status"],
        "current_stage":     run["current_stage"],
        "items_fetched":     run["items_fetched"],
        "items_after_dedup": run["items_after_dedup"],
        "items_in_digest":   run["items_in_digest"],
        "total_usd":         run["total_usd"],
        "error_message":     run["error_message"],
        "finished_at":       run["finished_at"],
    })


@bp.route("/costs")
@admin_required
def costs():
    repo = current_app.config["REPO"]
    bundle = current_app.config["BUNDLE"]
    days = int(request.args.get("days", 30))
    summary = repo.get_llm_costs_summary(bundle.config.feed_id, days=days)
    total_usd = sum(r["usd"] for r in summary)
    return render_template("admin/costs.html", summary=summary, total_usd=total_usd, days=days)


@bp.route("/schedule", methods=["GET", "POST"])
@admin_required
def schedule():
    app = current_app._get_current_object()
    repo = app.config["REPO"]
    bundle = app.config["BUNDLE"]
    feed_id = bundle.config.feed_id

    if request.method == "POST":
        new_time = (request.json or request.form).get("run_time", "").strip()
        # Validate HH:MM format
        try:
            h, m = new_time.split(":")
            assert 0 <= int(h) <= 23 and 0 <= int(m) <= 59
        except Exception:
            return jsonify({"error": "Invalid time — use HH:MM (24h)"}), 400

        repo.set_app_config(feed_id, "scheduler_run_time", new_time)

        # Reschedule the live APScheduler job if scheduler is running
        scheduler = app.config.get("SCHEDULER")
        if scheduler and scheduler.running:
            from apscheduler.triggers.cron import CronTrigger
            from zoneinfo import ZoneInfo
            tz = ZoneInfo(bundle.config.timezone)
            try:
                scheduler.reschedule_job(
                    "daily_pipeline",
                    trigger=CronTrigger(hour=int(h), minute=int(m), timezone=tz),
                )
            except Exception as exc:
                return jsonify({"error": f"Saved but reschedule failed: {exc}"}), 500

        return jsonify({"ok": True, "run_time": new_time})

    # GET — return current state
    run_time = repo.get_app_config(feed_id, "scheduler_run_time") or bundle.config.daily_run_time
    scheduler = app.config.get("SCHEDULER")
    next_run = None
    scheduler_running = False
    if scheduler and scheduler.running:
        scheduler_running = True
        job = scheduler.get_job("daily_pipeline")
        if job and job.next_run_time:
            next_run = job.next_run_time.isoformat()
    return jsonify({
        "run_time": run_time,
        "timezone": bundle.config.timezone,
        "next_run": next_run,
        "scheduler_running": scheduler_running,
    })


# ── Watchlist ──────────────────────────────────────────────────────────────────

@bp.route("/watchlist")
@admin_required
def watchlist():
    repo = current_app.config["REPO"]
    bundle = current_app.config["BUNDLE"]
    entries = repo.get_watchlist_entries(bundle.config.feed_id, enabled_only=False)
    import json as _json
    rows = []
    for e in entries:
        rows.append({
            "id": e["id"],
            "entry_type": e["entry_type"],
            "name": e["name"],
            "aliases": ", ".join(_json.loads(e["aliases"] or "[]")),
            "boost": e["boost"],
            "role": e["role"] or "",
            "notes": e["notes"] or "",
            "enabled": bool(e["enabled"]),
        })
    return render_template("admin/watchlist.html", entries=rows)


@bp.route("/watchlist/add", methods=["POST"])
@admin_required
def watchlist_add():
    import json as _json, re
    repo = current_app.config["REPO"]
    bundle = current_app.config["BUNDLE"]
    data = request.form
    name = data.get("name", "").strip()
    if not name:
        flash("Name is required.", "error")
        return redirect(url_for("admin.watchlist"))
    entry_id = re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")
    aliases_raw = data.get("aliases", "")
    aliases = [a.strip() for a in aliases_raw.split(",") if a.strip()]
    repo.upsert_watchlist_entry(bundle.config.feed_id, {
        "id": entry_id,
        "name": name,
        "entry_type": data.get("entry_type", "company"),
        "aliases": _json.dumps(aliases),
        "boost": float(data.get("boost", 1.5)),
        "role": data.get("role", ""),
        "notes": data.get("notes", ""),
        "enabled": 1,
    })
    flash(f"Added '{name}' to watchlist.", "info")
    return redirect(url_for("admin.watchlist"))


@bp.route("/watchlist/<entry_id>/edit", methods=["POST"])
@admin_required
def watchlist_edit(entry_id: str):
    import json as _json
    repo = current_app.config["REPO"]
    bundle = current_app.config["BUNDLE"]
    data = request.form
    aliases_raw = data.get("aliases", "")
    aliases = [a.strip() for a in aliases_raw.split(",") if a.strip()]
    name = data.get("name", entry_id)
    repo.upsert_watchlist_entry(bundle.config.feed_id, {
        "id": entry_id,
        "name": name,
        "entry_type": data.get("entry_type", "company"),
        "aliases": _json.dumps(aliases),
        "boost": float(data.get("boost", 1.5)),
        "role": data.get("role", ""),
        "notes": data.get("notes", ""),
        "enabled": int(data.get("enabled", "1")),
    })
    flash(f"Updated '{name}'.", "info")
    return redirect(url_for("admin.watchlist"))


@bp.route("/watchlist/<entry_id>/delete", methods=["POST"])
@admin_required
def watchlist_delete(entry_id: str):
    repo = current_app.config["REPO"]
    bundle = current_app.config["BUNDLE"]
    repo.delete_watchlist_entry(bundle.config.feed_id, entry_id)
    flash("Entry removed from watchlist.", "info")
    return redirect(url_for("admin.watchlist"))
