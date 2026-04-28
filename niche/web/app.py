from __future__ import annotations

import logging
import os

from flask import Flask, jsonify
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

from niche.web.user import User

logger = logging.getLogger(__name__)

csrf = CSRFProtect()
login_manager = LoginManager()


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__, template_folder="templates", static_folder="static")

    app.secret_key = os.environ.get("SESSION_SECRET") or "dev-secret-change-in-production"
    app.config["WTF_CSRF_ENABLED"] = True

    if config:
        app.config.update(config)

    csrf.init_app(app)

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

    @app.context_processor
    def theme_context() -> dict:
        bundle = app.config.get("BUNDLE")
        if not bundle:
            return {}

        # Convert hex accent to rgb components for CSS
        accent = bundle.config.accent_color.lstrip('#')
        try:
            r, g, b = int(accent[0:2], 16), int(accent[2:4], 16), int(accent[4:6], 16)
            accent_rgb = f"{r},{g},{b}"
        except Exception:
            accent_rgb = "192,57,43"

        # Get today's breaking items for ticker
        breaking_items = []
        try:
            from flask_login import current_user
            repo = app.config.get("REPO")
            if repo and current_user.is_authenticated:
                breaking_items = repo.get_breaking_items(bundle.config.feed_id, limit=8)
        except Exception:
            pass

        return {
            "feed_name": bundle.config.name,
            "feed_tagline": bundle.config.tagline,
            "accent_color": bundle.config.accent_color,
            "accent_rgb": accent_rgb,
            "logo_path": bundle.config.logo_path,
            "breaking_items": breaking_items,
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
        from apscheduler.triggers.cron import CronTrigger
        from zoneinfo import ZoneInfo

        hour, minute = bundle.config.daily_run_time.split(":")
        tz = ZoneInfo(bundle.config.timezone)
    except Exception as exc:
        logger.warning("Scheduler not started: %s", exc)
        return

    scheduler = BackgroundScheduler()

    def _run_pipeline() -> None:
        import uuid
        from niche.core.pipeline.runner import run_pipeline
        with app.app_context():
            repo = app.config.get("REPO")
            if repo:
                run_pipeline(bundle, repo, uuid.uuid4().hex)

    scheduler.add_job(
        _run_pipeline,
        CronTrigger(hour=int(hour), minute=int(minute), timezone=tz),
        id="daily_pipeline",
        replace_existing=True,
    )

    def _prune_read_log() -> None:
        with app.app_context():
            repo = app.config.get("REPO")
            if repo:
                repo.prune_read_log(days=180)

    scheduler.add_job(
        _prune_read_log,
        CronTrigger(day_of_week="sun", hour=3, minute=0, timezone=tz),
        id="weekly_prune_read_log",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "Scheduler started: daily pipeline at %s %s",
        bundle.config.daily_run_time,
        bundle.config.timezone,
    )
