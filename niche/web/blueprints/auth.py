from __future__ import annotations

import logging
import os

from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from niche.web.auth.magic_link import (
    is_token_expired,
    make_approval_token,
    make_login_link,
    token_expiry,
    validate_approval_token,
)
from niche.web.user import User

logger = logging.getLogger(__name__)
bp = Blueprint("auth", __name__)


@bp.route("/request", methods=["GET", "POST"])
def request_login():
    if current_user.is_authenticated:
        return redirect(url_for("digest.index"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not email or "@" not in email:
            return render_template("auth/request.html", error="Enter a valid email address.")

        repo = current_app.config["REPO"]
        bundle = current_app.config["BUNDLE"]

        user_row = repo.get_user_by_email(email)
        if not user_row:
            user_id = repo.create_user(email, bundle.config.feed_id)
            _send_approval_request(email, user_id, bundle, repo)
        else:
            if not user_row["is_approved"]:
                return render_template("auth/magic_link_sent.html", pending=True)

        expires_at = token_expiry()
        token = repo.create_magic_link_token(email, expires_at)
        app_url = current_app.config.get("APP_URL", request.host_url.rstrip("/"))
        link = make_login_link(token, app_url)
        _send_magic_link(email, link, bundle)

        return render_template("auth/magic_link_sent.html", pending=False)

    return render_template("auth/request.html")


@bp.route("/verify")
def verify():
    token = request.args.get("token", "")
    repo = current_app.config["REPO"]

    row = repo.get_magic_link_token(token)
    if not row or row["used"]:
        return render_template("auth/invalid_link.html")
    if is_token_expired(row["expires_at"]):
        return render_template("auth/invalid_link.html", expired=True)

    repo.mark_token_used(token)

    user_row = repo.get_user_by_email(row["email"])
    if not user_row:
        return render_template("auth/invalid_link.html")

    user = User(user_row)
    repo.update_last_seen(user.id)
    login_user(user, remember=True)
    return redirect(url_for("digest.index"))


@bp.route("/approve/<approval_token>")
def approve_user(approval_token: str):
    secret = current_app.config.get("APPROVAL_SECRET", os.environ.get("APPROVAL_SECRET", ""))
    user_id = validate_approval_token(approval_token, secret)
    if not user_id:
        return render_template("auth/invalid_link.html", expired=True)

    repo = current_app.config["REPO"]
    repo.approve_user(user_id)
    return render_template("auth/approved.html")


@bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.request_login"))


@bp.route("/unsubscribe/<token>")
def unsubscribe(token: str):
    from niche.web.auth.magic_link import validate_unsubscribe_token
    secret = current_app.config.get("APPROVAL_SECRET", os.environ.get("APPROVAL_SECRET", ""))
    user_id = validate_unsubscribe_token(token, secret)
    if not user_id:
        return render_template("auth/invalid_link.html")
    repo = current_app.config["REPO"]
    repo._conn.execute("UPDATE users SET email_enabled=0 WHERE id=?", (user_id,))
    repo._conn.commit()
    return render_template("auth/unsubscribed.html")


def _send_magic_link(email: str, link: str, bundle) -> None:
    provider = current_app.config.get("EMAIL_PROVIDER")
    if not provider:
        return
    html = render_template(
        "email/magic_link.html",
        link=link,
        feed_name=bundle.config.name,
        tagline=bundle.config.tagline,
    )
    try:
        provider.send(
            to=email,
            subject=f"Your {bundle.config.name} sign-in link",
            html=html,
            from_email=bundle.config.from_email,
        )
    except Exception as exc:
        logger.error("Failed to send magic link to %s: %s", email, exc)


def _send_approval_request(email: str, user_id: str, bundle, repo) -> None:
    provider = current_app.config.get("EMAIL_PROVIDER")
    if not provider:
        return
    secret = current_app.config.get("APPROVAL_SECRET", os.environ.get("APPROVAL_SECRET", ""))
    approval_token = make_approval_token(user_id, secret)
    app_url = current_app.config.get("APP_URL", "http://localhost:5000")
    approval_link = f"{app_url}/auth/approve/{approval_token}"

    admin_users = repo.get_admin_users(bundle.config.feed_id)
    html = render_template(
        "email/approval_request.html",
        email=email,
        approval_link=approval_link,
        feed_name=bundle.config.name,
    )
    for admin in admin_users:
        try:
            provider.send(
                to=admin["email"],
                subject=f"[{bundle.config.name}] New user approval request",
                html=html,
                from_email=bundle.config.from_email,
            )
        except Exception as exc:
            logger.error("Failed to send approval request: %s", exc)
