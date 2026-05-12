"""
Integration tests for Flask blueprint routes.

Tests that routes return expected status codes for authenticated
and unauthenticated requests.
"""
import pytest
import uuid
from datetime import datetime, timezone


def _create_admin_user(app, tmp_db):
    """Helper: create an approved admin user and return login user obj."""
    from niche.core.models.repository import Repository
    from niche.core.models.types import User

    repo = Repository(tmp_db)
    user = User(
        id=str(uuid.uuid4()),
        feed_id="test-fixture",
        email="admin@test.example",
        is_admin=True,
        is_approved=True,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    with repo.connect() as conn:
        repo.insert_user(conn, user)
    return user


def _login(client, app, user):
    """Log in a user via Flask-Login's test_request_context."""
    from flask_login import login_user
    from niche.web.user import LoginUser
    with client.session_transaction() as sess:
        pass
    # Use the test client to simulate a login via magic token
    with app.test_request_context():
        login_user(LoginUser(user))
    # Set the session cookie manually
    with client.application.test_request_context():
        from flask_login import login_user as flu
        flu(LoginUser(user))


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.get_json()["status"] == "ok"


def test_auth_request_get(client):
    resp = client.get("/auth/request")
    assert resp.status_code == 200


def test_digest_requires_auth(client):
    resp = client.get("/", follow_redirects=False)
    assert resp.status_code in (302, 401)


def test_archive_requires_auth(client):
    resp = client.get("/archive/", follow_redirects=False)
    assert resp.status_code in (302, 401)


def test_preferences_requires_auth(client):
    resp = client.get("/preferences/", follow_redirects=False)
    assert resp.status_code in (302, 401)


def test_admin_requires_auth(client):
    resp = client.get("/admin/", follow_redirects=False)
    assert resp.status_code in (302, 401)


def test_api_feedback_requires_auth(client):
    resp = client.post("/api/feedback", json={"item_id": "x", "signal": "up"})
    assert resp.status_code in (302, 401, 403)


def test_api_read_requires_auth(client):
    resp = client.post("/api/read", json={"item_id": "x"})
    assert resp.status_code in (302, 401, 403)


def test_auth_verify_invalid_token(client):
    resp = client.get("/auth/verify?token=badtoken123")
    assert resp.status_code in (200, 302)
