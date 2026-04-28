"""Integration tests for web routes (no real email sending)."""
from __future__ import annotations

import json
import pytest

from niche.web.app import create_app


@pytest.fixture
def app(bundle, repo):
    from niche.core.email.dev_provider import DevEmailProvider
    application = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "REPO": repo,
        "BUNDLE": bundle,
        "APP_URL": "http://localhost",
        "APPROVAL_SECRET": "test-secret",
        "EMAIL_PROVIDER": DevEmailProvider(),
    })
    return application


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def admin_user(repo, bundle):
    repo.upsert_user_admin("admin@example.com", bundle.config.feed_id)
    return repo.get_user_by_email("admin@example.com")


def _login(client, app, user_row):
    from niche.web.user import User
    from flask_login import login_user
    with app.test_request_context():
        pass
    with client.session_transaction() as sess:
        # Use Flask-Login's session key directly
        sess["_user_id"] = user_row["id"]
        sess["_fresh"] = True


class TestHealthRoute:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "ok"


class TestAuthRoutes:
    def test_request_login_page(self, client):
        resp = client.get("/auth/request")
        assert resp.status_code == 200
        assert b"Sign in" in resp.data

    def test_request_login_invalid_email(self, client):
        resp = client.post("/auth/request", data={"email": "notanemail"})
        assert resp.status_code == 200
        assert b"valid email" in resp.data

    def test_request_login_new_user(self, client, bundle):
        resp = client.post("/auth/request", data={"email": "newuser@example.com"})
        assert resp.status_code == 200
        assert b"pending" in resp.data.lower() or b"check your email" in resp.data.lower()

    def test_request_login_existing_approved_user(self, client, repo, bundle):
        repo.upsert_user_admin("approved@example.com", bundle.config.feed_id)
        resp = client.post("/auth/request", data={"email": "approved@example.com"})
        assert resp.status_code == 200

    def test_verify_valid_token(self, client, repo, bundle):
        repo.upsert_user_admin("verify@example.com", bundle.config.feed_id)
        from niche.web.auth.magic_link import token_expiry
        expires_at = token_expiry()
        token = repo.create_magic_link_token("verify@example.com", expires_at)
        resp = client.get(f"/auth/verify?token={token}", follow_redirects=True)
        assert resp.status_code == 200

    def test_verify_invalid_token(self, client):
        resp = client.get("/auth/verify?token=badtoken")
        assert resp.status_code == 200
        assert b"invalid" in resp.data.lower() or b"expired" in resp.data.lower()

    def test_verify_used_token(self, client, repo, bundle):
        repo.upsert_user_admin("used@example.com", bundle.config.feed_id)
        from niche.web.auth.magic_link import token_expiry
        token = repo.create_magic_link_token("used@example.com", token_expiry())
        repo.mark_token_used(token)
        resp = client.get(f"/auth/verify?token={token}")
        assert resp.status_code == 200
        assert b"invalid" in resp.data.lower() or b"expired" in resp.data.lower()

    def test_approve_valid_token(self, client, repo, bundle):
        repo.upsert_user_admin("admin2@example.com", bundle.config.feed_id)
        user = repo.get_user_by_email("admin2@example.com")
        from niche.web.auth.magic_link import make_approval_token
        token = make_approval_token(user["id"], "test-secret")
        resp = client.get(f"/auth/approve/{token}")
        assert resp.status_code == 200
        assert b"approved" in resp.data.lower()

    def test_approve_bad_token(self, client):
        resp = client.get("/auth/approve/badtoken")
        assert resp.status_code == 200
        assert b"invalid" in resp.data.lower() or b"expired" in resp.data.lower()


class TestDigestRoutes:
    def test_digest_redirects_unauthenticated(self, client):
        resp = client.get("/")
        assert resp.status_code == 302
        assert "/auth/request" in resp.headers["Location"]

    def test_digest_empty_state(self, client, app, admin_user):
        _login(client, app, admin_user)
        resp = client.get("/", follow_redirects=False)
        # Should either show empty state or digest
        assert resp.status_code in (200, 302)

    def test_item_detail_404(self, client, app, admin_user):
        _login(client, app, admin_user)
        resp = client.get("/item/nonexistent")
        assert resp.status_code == 404


class TestAdminRoutes:
    def test_admin_requires_login(self, client):
        resp = client.get("/admin/")
        assert resp.status_code == 302

    def test_admin_requires_admin_role(self, client, app, repo, bundle):
        repo.create_user("regular@example.com", bundle.config.feed_id)
        repo.approve_user(repo.get_user_by_email("regular@example.com")["id"])
        user = repo.get_user_by_email("regular@example.com")
        _login(client, app, user)
        resp = client.get("/admin/")
        assert resp.status_code == 403

    def test_admin_index_for_admin(self, client, app, admin_user):
        _login(client, app, admin_user)
        resp = client.get("/admin/")
        assert resp.status_code == 200
        assert b"pipeline" in resp.data.lower()

    def test_admin_sources(self, client, app, admin_user):
        _login(client, app, admin_user)
        resp = client.get("/admin/sources")
        assert resp.status_code == 200

    def test_admin_users(self, client, app, admin_user):
        _login(client, app, admin_user)
        resp = client.get("/admin/users")
        assert resp.status_code == 200

    def test_admin_costs(self, client, app, admin_user):
        _login(client, app, admin_user)
        resp = client.get("/admin/costs")
        assert resp.status_code == 200


class TestApiRoutes:
    def test_feedback_requires_login(self, client):
        resp = client.post("/api/feedback", json={"item_id": "x", "signal": "up"})
        assert resp.status_code in (302, 401)

    def test_feedback_invalid_signal(self, client, app, admin_user):
        _login(client, app, admin_user)
        resp = client.post("/api/feedback", json={"item_id": "x", "signal": "invalid"})
        assert resp.status_code == 400

    def test_export_data(self, client, app, admin_user):
        _login(client, app, admin_user)
        resp = client.get("/api/export")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "user" in data

    def test_mark_read_requires_item_id(self, client, app, admin_user):
        _login(client, app, admin_user)
        resp = client.post("/api/read", json={})
        assert resp.status_code == 400


class TestPreferencesRoutes:
    def test_preferences_requires_login(self, client):
        resp = client.get("/preferences/")
        assert resp.status_code == 302

    def test_preferences_page(self, client, app, admin_user):
        _login(client, app, admin_user)
        resp = client.get("/preferences/")
        assert resp.status_code == 200
        assert b"preferences" in resp.data.lower()

    def test_preferences_save(self, client, app, admin_user, bundle):
        _login(client, app, admin_user)
        form_data = {"keyword_blocks": "foo, bar", "keyword_boosts": ""}
        for topic in bundle.taxonomy.topics:
            form_data[f"topic_{topic.id}"] = "1.5"
        for region in bundle.taxonomy.regions:
            form_data[f"region_{region.id}"] = "0.8"
        resp = client.post("/preferences/", data=form_data, follow_redirects=True)
        assert resp.status_code == 200


class TestArchiveRoutes:
    def test_archive_requires_login(self, client):
        resp = client.get("/archive/")
        assert resp.status_code == 302

    def test_archive_empty(self, client, app, admin_user):
        _login(client, app, admin_user)
        resp = client.get("/archive/")
        assert resp.status_code == 200

    def test_archive_search(self, client, app, admin_user):
        _login(client, app, admin_user)
        resp = client.get("/archive/?q=test")
        assert resp.status_code == 200
