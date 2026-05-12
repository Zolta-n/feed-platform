"""
Auth blueprint — magic link sign-in, approval flow, logout, unsubscribe.

Routes:
  GET+POST /auth/request     — email submission + new-user registration
  GET      /auth/verify      — magic link token verification
  GET      /auth/logout      — session logout
  GET      /auth/approve/<approval_token> — one-click admin approval
  GET      /auth/unsubscribe/<token>      — unsubscribe from emails
"""
from __future__ import annotations

import datetime
import logging
import uuid

from flask import (
    Blueprint, current_app, flash, g, redirect, render_template,
    request, session, url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from ...core.models.types import User
from ..auth.magic_link import (
    generate_hmac_token, generate_magic_token, generate_unsubscribe_token,
    verify_hmac_token, verify_unsubscribe_token,
)
from ..forms import RequestLoginForm
from ..user import LoginUser

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


def _repo():
    return current_app.config["REPO"]


def _bundle():
    return current_app.config.get("BUNDLE")


def _get_db():
    from ..app import get_db
    return get_db()


def _send_magic_link(email: str, token: str) -> None:
    """Send the magic link email via configured provider."""
    app_url = current_app.config.get("APP_URL", "")
    link = f"{app_url}/auth/verify?token={token}"
    subject = "Your login link"
    try:
        template = current_app.jinja_env.get_template("email/magic_link.html")
        html = template.render(
            link=link,
            bundle=_bundle(),
            app_url=app_url,
        )
    except Exception:
        html = f'<p>Click to log in: <a href="{link}">{link}</a></p>'
    _send_email(email, subject, html)


def _send_approval_request(new_user: User) -> None:
    """Notify all admins that a new user is awaiting approval."""
    repo = _repo()
    bundle = _bundle()
    approval_secret = current_app.config.get("APPROVAL_SECRET", "")
    app_url = current_app.config.get("APP_URL", "")
    with repo.connect() as conn:
        admins = repo.get_admin_users(conn, new_user.feed_id)
    for admin in admins:
        token = generate_hmac_token(new_user.id, approval_secret, expiry_seconds=259200)
        approve_url = f"{app_url}/auth/approve/{token}?uid={new_user.id}"
        subject = f"New access request: {new_user.email}"
        try:
            template = current_app.jinja_env.get_template("email/approval_request.html")
            html = template.render(
                new_user=new_user,
                approve_url=approve_url,
                bundle=bundle,
                app_url=app_url,
            )
        except Exception:
            html = (
                f"<p>{new_user.email} has requested access.</p>"
                f'<p><a href="{approve_url}">Approve</a></p>'
            )
        _send_email(admin.email, subject, html)


def _send_email(to: str, subject: str, html: str) -> None:
    provider_name = current_app.config.get("EMAIL_PROVIDER", "dev")
    bundle = _bundle()
    from_email = bundle.config.from_email if bundle else "noreply@localhost"
    try:
        if provider_name == "resend":
            import resend
            resend.Emails.send({
                "from": from_email,
                "to": to,
                "subject": subject,
                "html": html,
            })
        else:
            logger.info("[DevEmail] To=%s Subject=%s", to, subject)
    except Exception as exc:
        logger.error("Email send error to %s: %s", to, exc)


@auth_bp.route("/request", methods=["GET", "POST"])
def request_login():
    if current_user.is_authenticated:
        return redirect(url_for("digest.index"))

    form = RequestLoginForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        repo = _repo()
        bundle = _bundle()
        feed_id = bundle.config.feed_id if bundle else "default"
        with repo.connect() as conn:
            existing = repo.get_user_by_email(conn, email)
        if existing is None:
            # New user — create with is_approved=0
            new_user = User(
                id=str(uuid.uuid4()),
                feed_id=feed_id,
                email=email,
                is_admin=False,
                is_approved=False,
                created_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            )
            with repo.connect() as conn:
                repo.insert_user(conn, new_user)
            _send_approval_request(new_user)
            return render_template(
                "auth/magic_link_sent.html",
                email=email,
                pending=True,
            )
        elif not existing.is_approved:
            return render_template(
                "auth/magic_link_sent.html",
                email=email,
                pending=True,
            )
        else:
            # Approved user — send magic link
            token = generate_magic_token()
            expires_at = (
                datetime.datetime.now(datetime.timezone.utc)
                + datetime.timedelta(minutes=15)
            ).isoformat()
            with repo.connect() as conn:
                repo.create_magic_token(conn, token, email, expires_at)
            _send_magic_link(email, token)
            return render_template(
                "auth/magic_link_sent.html",
                email=email,
                pending=False,
            )

    return render_template("auth/request.html", form=form)


@auth_bp.route("/verify")
def verify():
    token = request.args.get("token", "")
    repo = _repo()
    if not token:
        flash("Invalid login link.", "error")
        return redirect(url_for("auth.request_login"))

    with repo.connect() as conn:
        tok = repo.get_magic_token(conn, token)
    if not tok:
        return render_template("auth/invalid_link.html", bundle=_bundle())
    if tok["used"]:
        return render_template("auth/invalid_link.html", bundle=_bundle())
    expires_at = datetime.datetime.fromisoformat(tok["expires_at"].replace("Z", "+00:00"))
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
    if datetime.datetime.now(datetime.timezone.utc) > expires_at:
        return render_template("auth/invalid_link.html", bundle=_bundle())

    # Valid token — log the user in
    with repo.connect() as conn:
        repo.consume_magic_token(conn, token)
        user = repo.get_user_by_email(conn, tok["email"])
    if not user or not user.is_approved:
        return render_template("auth/invalid_link.html", bundle=_bundle())

    login_user(LoginUser(user), remember=False)
    with repo.connect() as conn:
        repo.touch_user(conn, user.id)
    return redirect(url_for("digest.index"))


@auth_bp.route("/dev-login")
def dev_login():
    """One-click login for local dev only — disabled when EMAIL_PROVIDER=prod."""
    if current_app.config.get("EMAIL_PROVIDER") == "prod":
        from flask import abort
        abort(404)
    email = request.args.get("email", "")
    repo = _repo()
    with repo.connect() as conn:
        if email:
            user = repo.get_user_by_email(conn, email)
        else:
            # Default to first approved admin
            user = repo.get_first_admin(conn)
    if not user or not user.is_approved:
        return "No approved user found. Create one via the admin or seed the DB.", 400
    login_user(LoginUser(user), remember=True)
    with repo.connect() as conn:
        repo.touch_user(conn, user.id)
    return redirect(url_for("digest.index"))


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.request_login"))


@auth_bp.route("/approve/<approval_token>")
def approve_user(approval_token: str):
    uid = request.args.get("uid", "")
    approval_secret = current_app.config.get("APPROVAL_SECRET", "")
    if not verify_hmac_token(approval_token, uid, approval_secret):
        flash("Invalid or expired approval link.", "error")
        return render_template("auth/invalid_link.html", bundle=_bundle())

    repo = _repo()
    bundle = _bundle()
    with repo.connect() as conn:
        user = repo.get_user(conn, uid)
    if not user:
        flash("User not found.", "error")
        return redirect(url_for("auth.request_login"))

    user.is_approved = True
    with repo.connect() as conn:
        repo.update_user(conn, user)

    # Send welcome magic link to the newly approved user
    token = generate_magic_token()
    expires_at = (
        datetime.datetime.now(datetime.timezone.utc)
        + datetime.timedelta(minutes=15)
    ).isoformat()
    with repo.connect() as conn:
        repo.create_magic_token(conn, token, user.email, expires_at)
    _send_magic_link(user.email, token)

    return render_template("auth/approved.html", email=user.email, bundle=bundle)


@auth_bp.route("/unsubscribe/<token>")
def unsubscribe(token: str):
    approval_secret = current_app.config.get("APPROVAL_SECRET", "")
    user_id = verify_unsubscribe_token(token, approval_secret)
    if not user_id:
        flash("Invalid unsubscribe link.", "error")
        return redirect(url_for("auth.request_login"))

    repo = _repo()
    with repo.connect() as conn:
        user = repo.get_user(conn, user_id)
    if not user:
        return render_template("auth/unsubscribed.html", bundle=_bundle())

    user.email_enabled = False
    with repo.connect() as conn:
        repo.update_user(conn, user)

    return render_template("auth/unsubscribed.html", bundle=_bundle())
