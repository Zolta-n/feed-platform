from __future__ import annotations

import logging
import os

from flask import Flask, jsonify
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

from niche.web.template_filters import as_bullets
from niche.web.user import User

logger = logging.getLogger(__name__)

csrf = CSRFProtect()
login_manager = LoginManager()


def _static_version() -> str:
    import subprocess, time
    try:
        base = subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
        # Append epoch-minutes so each restart busts the cache during development
        return f"{base}-{int(time.time()) // 60}"
    except Exception:
        return str(int(time.time()))


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")

    app.secret_key = os.environ.get("SESSION_SECRET") or "dev-secret-change-in-production"
    app.config["WTF_CSRF_ENABLED"] = True
    app.config["STATIC_VERSION"] = _static_version()

    if config:
        app.config.update(config)

    csrf.init_app(app)
    app.add_template_filter(as_bullets, name="as_bullets")

    login_manager.init_app(app)
    login_manager.login_view = "auth.request_login"
    login_manager.login_message = "Please sign in to continue."
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id: str) -> User | None:
        repo = app.config.get("REPO")
        if not repo:
            return None
        row = repo.get_user_by_id(user_id)
        return User(row) if row else None

    _THEME_HEX = {
        "red":    "#c0392b",
        "blue":   "#2563eb",
        "amber":  "#d97706",
        "purple": "#7c3aed",
        "teal":   "#0d9488",
    }

    @app.context_processor
    def theme_context() -> dict:
        bundle = app.config.get("BUNDLE")
        if not bundle:
            return {}

        # Default accent from bundle config
        accent_hex = bundle.config.accent_color

        # Override with user's saved theme preference if logged in
        breaking_items = []
        try:
            from flask_login import current_user
            repo = app.config.get("REPO")
            if repo and current_user.is_authenticated:
                prefs = repo.get_user_preferences(current_user.id)
                if prefs:
                    try:
                        tc = prefs["theme_color"]
                        if tc and tc in _THEME_HEX:
                            accent_hex = _THEME_HEX[tc]
                    except (KeyError, TypeError):
                        pass
                breaking_items = repo.get_breaking_items(bundle.config.feed_id, limit=8)
        except Exception:
            pass

        accent = accent_hex.lstrip("#")
        try:
            r, g, b = int(accent[0:2], 16), int(accent[2:4], 16), int(accent[4:6], 16)
            accent_rgb = f"{r},{g},{b}"
        except Exception:
            accent_rgb = "192,57,43"

        return {
            "feed_name": bundle.config.name,
            "feed_tagline": bundle.config.tagline,
            "accent_color": accent_hex,
            "accent_rgb": accent_rgb,
            "logo_path": bundle.config.logo_path,
            "breaking_items": breaking_items,
            "static_version": app.config.get("STATIC_VERSION", "1"),
        }

    from niche.web.blueprints.digest import bp as digest_bp
    from niche.web.blueprints.auth import bp as auth_bp
    from niche.web.blueprints.preferences import bp as prefs_bp
    from niche.web.blueprints.archive import bp as archive_bp
    from niche.web.blueprints.api import bp as api_bp
    from niche.web.blueprints.admin import bp as admin_bp
    from niche.web.blueprints.share import bp as share_bp

    app.register_blueprint(digest_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(prefs_bp, url_prefix="/preferences")
    app.register_blueprint(archive_bp, url_prefix="/archive")
    app.register_blueprint(api_bp, url_prefix="/api")
    app.register_blueprint(admin_bp, url_prefix="/admin")
    app.register_blueprint(share_bp)

    @app.route("/health")
    def health():
        return jsonify({"status": "ok"})

    bundle = app.config.get("BUNDLE")
    if bundle and os.environ.get("SCHEDULER_ENABLED", "").lower() == "true":
        _start_scheduler(app, bundle)

    return app


def _start_scheduler(app: Flask, bundle) -> None:
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore
        from apscheduler.triggers.cron import CronTrigger
        from zoneinfo import ZoneInfo

        db_path = app.config.get("DB_PATH", "niche.db")
        repo = app.config.get("REPO")

        # DB override takes precedence over bundle config
        run_time = bundle.config.daily_run_time
        if repo:
            override = repo.get_app_config(bundle.config.feed_id, "scheduler_run_time")
            if override:
                run_time = override

        hour, minute = run_time.split(":")
        tz = ZoneInfo(bundle.config.timezone)
    except Exception as exc:
        logger.warning("Scheduler not started: %s", exc)
        return

    scheduler = BackgroundScheduler(
        jobstores={"default": SQLAlchemyJobStore(url=f"sqlite:///{db_path}")},
        job_defaults={"misfire_grace_time": 3600},
    )
    # Store reference so admin can reschedule without restart
    app.config["SCHEDULER"] = scheduler

    def _run_pipeline() -> None:
        import uuid
        from niche.core.pipeline.runner import run_pipeline
        from niche.core.models.repository import Repository as _Repo
        with app.app_context():
            worker_repo = _Repo(db_path)
            try:
                run_pipeline(bundle, worker_repo, uuid.uuid4().hex)
            finally:
                worker_repo.close()

    scheduler.add_job(
        _run_pipeline,
        CronTrigger(hour=int(hour), minute=int(minute), timezone=tz),
        id="daily_pipeline",
        replace_existing=True,
    )

    def _prune_read_log() -> None:
        from niche.core.models.repository import Repository as _Repo
        with app.app_context():
            worker_repo = _Repo(db_path)
            try:
                worker_repo.prune_read_log(days=180)
            finally:
                worker_repo.close()

    scheduler.add_job(
        _prune_read_log,
        CronTrigger(day_of_week="sun", hour=3, minute=0, timezone=tz),
        id="weekly_prune_read_log",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("Scheduler started: daily pipeline at %s %s", run_time, bundle.config.timezone)
