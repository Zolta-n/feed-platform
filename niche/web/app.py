"""
Flask application factory.

create_app(config=None) wires together:
- All blueprints (digest, admin, api, archive, preferences, auth, share)
- Flask-Login
- Flask-WTF CSRF
- APScheduler (optional, controlled by SCHEDULER_ENABLED)
- Feed bundle loaded from FEED_DIR / NICHE_FEED_DIR env var
- Repository initialised from DB_PATH / NICHE_DB_PATH env var

Config keys (from env or passed dict):
  FEED_DIR, DB_PATH, SESSION_SECRET, APP_URL, STATIC_VERSION,
  WTF_CSRF_ENABLED, SCHEDULER_ENABLED, EMAIL_PROVIDER,
  PYTHON_EXECUTABLE, PYTHONPATH, APPROVAL_SECRET
"""
from __future__ import annotations

import logging
import os
import sqlite3
from typing import Optional

from flask import Flask, g, redirect, url_for
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

from ..core.bundle_loader import load_bundle
from ..core.models.repository import Repository
from ..core.models.schema import init_db
from .user import LoginUser

logger = logging.getLogger(__name__)

login_manager = LoginManager()
csrf = CSRFProtect()

THEME_COLORS = {
    "red":    "#E63946",
    "blue":   "#4361EE",
    "amber":  "#F4A261",
    "purple": "#9B5DE5",
    "teal":   "#0d9488",
}


def get_db() -> sqlite3.Connection:
    """Return the per-request DB connection, opening it if needed."""
    if "db" not in g:
        db_path = g._app_db_path
        g.db = sqlite3.connect(db_path)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys=ON")
    return g.db


def create_app(config: Optional[dict] = None) -> Flask:
    """Flask application factory."""
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
    )

    # ------------------------------------------------------------------ Config
    app.config["SECRET_KEY"] = os.environ.get("SESSION_SECRET", "dev-secret-change-me")
    app.config["WTF_CSRF_ENABLED"] = os.environ.get("WTF_CSRF_ENABLED", "true").lower() != "false"
    app.config["SESSION_COOKIE_HTTPONLY"] = True
    app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
    app.config["STATIC_VERSION"] = os.environ.get("STATIC_VERSION", "1")
    app.config["APP_URL"] = os.environ.get("APP_URL", "http://localhost:5000")
    app.config["EMAIL_PROVIDER"] = os.environ.get("EMAIL_PROVIDER", "dev")
    app.config["APPROVAL_SECRET"] = os.environ.get(
        "APPROVAL_SECRET", app.config["SECRET_KEY"]
    )
    app.config["PYTHON_EXECUTABLE"] = os.environ.get("PYTHON_EXECUTABLE", "python3")
    app.config["PYTHONPATH"] = os.environ.get("PYTHONPATH", "")
    app.config["SCHEDULER_ENABLED"] = os.environ.get("SCHEDULER_ENABLED", "false").lower() == "true"

    db_path = os.environ.get("NICHE_DB_PATH") or os.environ.get("DB_PATH", "niche.db")
    app.config["DB_PATH"] = db_path

    feed_dir = os.environ.get("NICHE_FEED_DIR") or os.environ.get("FEED_DIR", "feeds/brake-by-wire")
    app.config["FEED_DIR"] = feed_dir

    if config:
        app.config.update(config)

    # ------------------------------------------------------------------ DB init
    init_db(app.config["DB_PATH"])

    # ------------------------------------------------------------ Feed bundle
    try:
        bundle = load_bundle(app.config["FEED_DIR"])
        app.config["BUNDLE"] = bundle
        # Sync sources table from bundle
        repo = Repository(app.config["DB_PATH"])
        with repo.connect() as conn:
            for src_cfg in bundle.sources:
                repo.upsert_source(conn, src_cfg, bundle.config.feed_id)
        app.config["REPO"] = repo
        logger.info("Feed bundle loaded: %s", bundle.config.feed_id)
    except Exception as exc:
        logger.error("Failed to load feed bundle from %s: %s", feed_dir, exc)
        # Create a minimal placeholder so the app starts
        app.config["BUNDLE"] = None
        app.config["REPO"] = Repository(app.config["DB_PATH"])

    # ----------------------------------------------------------- Flask-Login
    login_manager.init_app(app)
    login_manager.login_view = "auth.request_login"
    login_manager.login_message = "Please log in to access this page."
    login_manager.login_message_category = "info"

    @login_manager.user_loader
    def load_user(user_id: str):
        repo = app.config["REPO"]
        with repo.connect() as conn:
            user = repo.get_user(conn, user_id)
        if user and not user.deleted_at:
            return LoginUser(user)
        return None

    # ------------------------------------------------------------------- CSRF
    csrf.init_app(app)

    # ----------------------------------------------- Per-request DB setup
    @app.before_request
    def _open_db():
        g._app_db_path = app.config["DB_PATH"]

    @app.before_request
    def _load_user_theme():
        from flask_login import current_user as cu
        if cu.is_authenticated:
            try:
                repo = app.config["REPO"]
                with repo.connect() as conn:
                    prefs = repo.get_preferences(conn, cu.id)
                if prefs:
                    cu.theme_color = prefs.theme_color
            except Exception:
                pass

    @app.teardown_appcontext
    def _close_db(exc=None):
        db = g.pop("db", None)
        if db is not None:
            db.close()

    # ------------------------------------------ Jinja2 filters / globals
    import json as _json
    from flask_wtf.csrf import generate_csrf as _generate_csrf
    from markupsafe import Markup as _Markup

    app.jinja_env.globals.update(len=len, min=min, max=max, int=int, round=round)

    @app.template_filter("fromjson")
    def fromjson_filter(s):
        if isinstance(s, (list, dict)):
            return s  # already deserialized
        try:
            return _json.loads(s) if s else []
        except Exception:
            return []

    # ------------------------------------------ Template context processor
    @app.context_processor
    def inject_globals():
        bundle = app.config.get("BUNDLE")
        feed_name = bundle.config.name if bundle else "Feed"
        feed_tagline = bundle.config.tagline if bundle else ""
        try:
            csrf_field = _Markup(f'<input type="hidden" name="csrf_token" value="{_generate_csrf()}">')
        except Exception:
            csrf_field = _Markup("")
        return {
            "bundle": bundle,
            "feed_name": feed_name,
            "feed_tagline": feed_tagline,
            "static_version": app.config.get("STATIC_VERSION", "1"),
            "theme_colors": THEME_COLORS,
            "app_url": app.config.get("APP_URL", ""),
            "csrf_token_field": csrf_field,
        }

    # ------------------------------------------------------------- Blueprints
    from .blueprints.auth import auth_bp
    from .blueprints.digest import digest_bp
    from .blueprints.admin import admin_bp
    from .blueprints.api import api_bp
    from .blueprints.archive import archive_bp
    from .blueprints.preferences import preferences_bp
    from .blueprints.share import share_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(digest_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(archive_bp)
    app.register_blueprint(preferences_bp)
    app.register_blueprint(share_bp)

    # ---------------------------------------------------------- Health check
    @app.route("/health")
    def health():
        return {"status": "ok"}, 200

    # ----------------------------------------------------------- APScheduler
    if app.config.get("SCHEDULER_ENABLED"):
        _init_scheduler(app)

    return app


def _init_scheduler(app: Flask) -> None:
    """Configure and start APScheduler inside the Flask process."""
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

        jobstores = {
            "default": SQLAlchemyJobStore(
                url=f"sqlite:///{app.config['DB_PATH']}"
            )
        }
        scheduler = BackgroundScheduler(jobstores=jobstores)
        bundle = app.config.get("BUNDLE")
        if bundle:
            run_time = bundle.config.daily_run_time  # "HH:MM"
            tz = bundle.config.timezone
            hour, minute = (int(x) for x in run_time.split(":"))
            scheduler.add_job(
                _trigger_pipeline,
                "cron",
                hour=hour,
                minute=minute,
                timezone=tz,
                id="daily_pipeline",
                replace_existing=True,
                args=[app],
                misfire_grace_time=3600,
            )
        scheduler.start()
        app.config["SCHEDULER"] = scheduler
        logger.info("APScheduler started")
    except Exception as exc:
        logger.error("APScheduler init failed: %s", exc)
        app.config["SCHEDULER"] = None


def _trigger_pipeline(app: Flask) -> None:
    """Called by APScheduler to kick off the daily pipeline run."""
    import subprocess
    import sys

    python = app.config.get("PYTHON_EXECUTABLE") or sys.executable
    feed_dir = app.config.get("FEED_DIR", "feeds/brake-by-wire")
    db_path = app.config.get("DB_PATH", "niche.db")
    env = os.environ.copy()
    pythonpath = app.config.get("PYTHONPATH", "")
    if pythonpath:
        env["PYTHONPATH"] = pythonpath

    logger.info("APScheduler: triggering pipeline run")
    try:
        proc = subprocess.Popen(
            [python, "cli.py", "pipeline", "run",
             "--feed-dir", feed_dir, "--db-path", db_path],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        stdout, _ = proc.communicate(timeout=3600)
        if proc.returncode != 0:
            logger.error("Pipeline subprocess failed:\n%s", stdout.decode())
        else:
            logger.info("Pipeline subprocess completed successfully")
    except Exception as exc:
        logger.error("Pipeline subprocess error: %s", exc)
