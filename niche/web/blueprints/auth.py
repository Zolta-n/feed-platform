from __future__ import annotations

import logging
import os

from flask import (
    Blueprint,
    current_app,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from niche.web.auth.magic_link import (
    MIN_PASSWORD_LENGTH,
    hash_password,
    is_token_expired,
    make_approval_token,
    make_login_link,
    password_attempt_blocked,
    record_password_failure,
    reset_password_attempts,
    token_expiry,
    validate_approval_token,
    validate_password_strength,
    verify_password,
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
        password = request.form.get("password", "")

        if not email or "@" not in email:
            return render_template("auth/request.html", error="Enter a valid email address.")

        repo = current_app.config["REPO"]
        bundle = current_app.config["BUNDLE"]

        user_row = repo.get_user_by_email(email)

        # Password sign-in path: approved user + non-empty password field + hash set.
        if user_row and user_row["is_approved"] and password:
            if password_attempt_blocked(email):
                return render_template(
                    "auth/request.html",
                    email=email,
                    error="Too many failed attempts. Please use the email sign-in link below.",
                )
            stored_hash = None
            try:
                stored_hash = user_row["password_hash"]
            except (KeyError, IndexError):
                stored_hash = None
            if stored_hash and verify_password(password, stored_hash):
                reset_password_attempts(email)
                user = User(user_row)
                repo.update_last_seen(user.id)
                login_user(user, remember=True)
                return redirect(url_for("digest.index"))
            record_password_failure(email)
            return render_template(
                "auth/request.html",
                email=email,
                error="Incorrect email or password.",
            )

        if not user_row:
            user_id = repo.create_user(email, bundle.config.feed_id)
            if current_app.config.get("EMAIL_PROVIDER"):
                _send_approval_request(email, user_id, bundle, repo)
            else:
                # Dev mode: auto-approve new users so the login flow isn't blocked
                repo.approve_user(user_id)
        else:
            if not user_row["is_approved"]:
                return render_template("auth/magic_link_sent.html", pending=True)

        expires_at = token_expiry()
        token = repo.create_magic_link_token(email, expires_at)
        app_url = current_app.config.get("APP_URL", request.host_url.rstrip("/"))
        link = make_login_link(token, app_url)

        # Dev mode: no email provider → redirect directly to the verify URL
        if not current_app.config.get("EMAIL_PROVIDER"):
            logger.warning("DEV MODE — no email provider, redirecting %s directly", email)
            from urllib.parse import urlparse
            parsed = urlparse(link)
            return redirect(f"{parsed.path}?{parsed.query}")

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

    has_password = False
    try:
        has_password = bool(user_row["password_hash"])
    except (KeyError, IndexError):
        has_password = False
    if not has_password:
        session["prompt_set_password"] = True
        return redirect(url_for("auth.set_password"))
    return redirect(url_for("digest.index"))


@bp.route("/set-password", methods=["GET", "POST"])
@login_required
def set_password():
    repo = current_app.config["REPO"]
    prompt = session.pop("prompt_set_password", False)

    if request.method == "POST":
        if request.form.get("skip"):
            return redirect(url_for("digest.index"))

        new_password = request.form.get("new_password", "")
        confirm = request.form.get("confirm_password", "")
        if new_password != confirm:
            return render_template(
                "auth/set_password.html",
                prompt=prompt,
                error="Passwords do not match.",
                min_length=MIN_PASSWORD_LENGTH,
            )
        err = validate_password_strength(new_password)
        if err:
            return render_template(
                "auth/set_password.html",
                prompt=prompt,
                error=err,
                min_length=MIN_PASSWORD_LENGTH,
            )

        repo.set_password_hash(current_user.id, hash_password(new_password))
        repo.invalidate_magic_links_for_email(current_user.email)
        reset_password_attempts(current_user.email)
        return redirect(url_for("digest.index"))

    return render_template(
        "auth/set_password.html",
        prompt=prompt,
        min_length=MIN_PASSWORD_LENGTH,
    )


@bp.route("/remove-password", methods=["POST"])
@login_required
def remove_password():
    repo = current_app.config["REPO"]
    repo.set_password_hash(current_user.id, None)
    return redirect(url_for("preferences.index"))


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
        logger.warning("DEV MODE — no email provider. Magic link for %s:\n%s", email, link)
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
