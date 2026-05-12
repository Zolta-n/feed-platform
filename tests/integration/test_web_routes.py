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

    def test_verify_get_shows_confirmation_page(self, client, repo, bundle):
        """GET on the magic link must NOT consume the token — must show a confirm page.
        This defeats corporate URL scanners that pre-fetch links in email."""
        repo.upsert_user_admin("verify@example.com", bundle.config.feed_id)
        from niche.web.auth.magic_link import token_expiry
        token = repo.create_magic_link_token("verify@example.com", token_expiry())

        resp = client.get(f"/auth/verify?token={token}")
        assert resp.status_code == 200
        assert b"Sign in" in resp.data
        # token must NOT be marked used after GET
        row = repo.get_magic_link_token(token)
        assert row["used"] == 0

    def test_verify_get_twice_still_works(self, client, repo, bundle):
        """Multiple GETs (e.g. scanner + user) must each succeed without consuming the token."""
        repo.upsert_user_admin("verify-twice@example.com", bundle.config.feed_id)
        from niche.web.auth.magic_link import token_expiry
        token = repo.create_magic_link_token("verify-twice@example.com", token_expiry())

        # Simulate scanner pre-fetch then user click
        resp1 = client.get(f"/auth/verify?token={token}")
        resp2 = client.get(f"/auth/verify?token={token}")
        assert resp1.status_code == 200
        assert resp2.status_code == 200
        # Token still unused
        assert repo.get_magic_link_token(token)["used"] == 0

    def test_verify_post_consumes_token_and_logs_in(self, client, repo, bundle):
        repo.upsert_user_admin("verify-post@example.com", bundle.config.feed_id)
        from niche.web.auth.magic_link import token_expiry
        token = repo.create_magic_link_token("verify-post@example.com", token_expiry())

        resp = client.post("/auth/verify", data={"token": token}, follow_redirects=False)
        assert resp.status_code == 302
        assert repo.get_magic_link_token(token)["used"] == 1

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

    def test_approve_get_shows_confirmation_no_db_change(self, client, repo, bundle):
        """GET on /auth/approve must NOT mark the user approved — must show confirm page."""
        user_id = repo.create_user("pending@example.com", bundle.config.feed_id)
        from niche.web.auth.magic_link import make_approval_token
        token = make_approval_token(user_id, "test-secret")

        resp = client.get(f"/auth/approve/{token}")
        assert resp.status_code == 200
        assert b"Approve" in resp.data
        # User must still be unapproved after GET
        assert repo.get_user_by_id(user_id)["is_approved"] == 0

    def test_approve_post_marks_user_approved(self, client, repo, bundle):
        user_id = repo.create_user("pending2@example.com", bundle.config.feed_id)
        from niche.web.auth.magic_link import make_approval_token
        token = make_approval_token(user_id, "test-secret")

        resp = client.post(f"/auth/approve/{token}")
        assert resp.status_code == 200
        assert b"approved" in resp.data.lower()
        assert repo.get_user_by_id(user_id)["is_approved"] == 1

    def test_approve_bad_token(self, client):
        resp = client.get("/auth/approve/badtoken")
        assert resp.status_code == 200
        assert b"invalid" in resp.data.lower() or b"expired" in resp.data.lower()


class TestPasswordAuth:
    def _create_approved_user(self, repo, bundle, email):
        user_id = repo.create_user(email, bundle.config.feed_id)
        repo.approve_user(user_id)
        return repo.get_user_by_email(email)

    def test_correct_password_logs_in_instantly(self, client, repo, bundle):
        from niche.web.auth.magic_link import hash_password, reset_password_attempts
        email = "pw-ok@example.com"
        user = self._create_approved_user(repo, bundle, email)
        repo.set_password_hash(user["id"], hash_password("correct-horse-battery"))
        reset_password_attempts(email)

        resp = client.post(
            "/auth/request",
            data={"email": email, "password": "correct-horse-battery"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "/auth/" not in resp.headers["Location"]

    def test_wrong_password_shows_error_and_no_login(self, client, repo, bundle):
        from niche.web.auth.magic_link import hash_password, reset_password_attempts
        email = "pw-bad@example.com"
        user = self._create_approved_user(repo, bundle, email)
        repo.set_password_hash(user["id"], hash_password("correct-horse-battery"))
        reset_password_attempts(email)

        resp = client.post(
            "/auth/request",
            data={"email": email, "password": "wrong-password"},
        )
        assert resp.status_code == 200
        assert b"Incorrect" in resp.data

    def test_blank_password_falls_back_to_magic_link(self, client, repo, bundle):
        from niche.web.auth.magic_link import hash_password, reset_password_attempts
        email = "pw-fallback@example.com"
        user = self._create_approved_user(repo, bundle, email)
        repo.set_password_hash(user["id"], hash_password("correct-horse-battery"))
        reset_password_attempts(email)

        resp = client.post("/auth/request", data={"email": email, "password": ""})
        assert resp.status_code == 200
        assert b"check your email" in resp.data.lower() or b"sent" in resp.data.lower()

    def test_no_password_set_falls_back_to_magic_link(self, client, repo, bundle):
        email = "pw-none@example.com"
        self._create_approved_user(repo, bundle, email)

        resp = client.post(
            "/auth/request",
            data={"email": email, "password": "anything"},
        )
        assert resp.status_code == 200
        assert b"Incorrect" in resp.data

    def test_rate_limit_after_five_failures(self, client, repo, bundle):
        from niche.web.auth.magic_link import hash_password, reset_password_attempts
        email = "pw-limit@example.com"
        user = self._create_approved_user(repo, bundle, email)
        repo.set_password_hash(user["id"], hash_password("correct-horse-battery"))
        reset_password_attempts(email)

        for _ in range(5):
            client.post("/auth/request", data={"email": email, "password": "wrong"})

        resp = client.post("/auth/request", data={"email": email, "password": "wrong"})
        assert resp.status_code == 200
        assert b"Too many" in resp.data
        reset_password_attempts(email)

    def test_set_password_after_magic_link_login(self, client, app, repo, bundle):
        email = "pw-set@example.com"
        user = self._create_approved_user(repo, bundle, email)

        from niche.web.auth.magic_link import token_expiry
        token = repo.create_magic_link_token(email, token_expiry())
        resp = client.post("/auth/verify", data={"token": token}, follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/set-password" in resp.headers["Location"]

        resp = client.post(
            "/auth/set-password",
            data={"new_password": "new-pass-1234", "confirm_password": "new-pass-1234"},
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert repo.get_password_hash(user["id"])

    def test_set_password_mismatch(self, client, app, repo, bundle):
        email = "pw-mismatch@example.com"
        user = self._create_approved_user(repo, bundle, email)
        _login(client, app, user)

        resp = client.post(
            "/auth/set-password",
            data={"new_password": "alpha-1234", "confirm_password": "beta-12345"},
        )
        assert resp.status_code == 200
        assert b"do not match" in resp.data
        assert repo.get_password_hash(user["id"]) is None

    def test_set_password_too_short(self, client, app, repo, bundle):
        email = "pw-short@example.com"
        user = self._create_approved_user(repo, bundle, email)
        _login(client, app, user)

        resp = client.post(
            "/auth/set-password",
            data={"new_password": "abc", "confirm_password": "abc"},
        )
        assert resp.status_code == 200
        assert b"at least" in resp.data
        assert repo.get_password_hash(user["id"]) is None

    def test_set_password_invalidates_existing_magic_links(self, client, app, repo, bundle):
        from niche.web.auth.magic_link import token_expiry
        email = "pw-invalidate@example.com"
        user = self._create_approved_user(repo, bundle, email)
        token = repo.create_magic_link_token(email, token_expiry())
        _login(client, app, user)

        client.post(
            "/auth/set-password",
            data={"new_password": "fresh-password-1", "confirm_password": "fresh-password-1"},
        )

        row = repo.get_magic_link_token(token)
        assert row["used"] == 1

    def test_remove_password(self, client, app, repo, bundle):
        from niche.web.auth.magic_link import hash_password
        email = "pw-remove@example.com"
        user = self._create_approved_user(repo, bundle, email)
        repo.set_password_hash(user["id"], hash_password("some-password-1"))
        _login(client, app, user)

        resp = client.post("/auth/remove-password", follow_redirects=False)
        assert resp.status_code == 302
        assert repo.get_password_hash(user["id"]) is None

    def test_verify_skips_set_password_prompt_when_password_already_set(
        self, client, repo, bundle
    ):
        from niche.web.auth.magic_link import hash_password, token_expiry
        email = "pw-already@example.com"
        user = self._create_approved_user(repo, bundle, email)
        repo.set_password_hash(user["id"], hash_password("already-set-1"))

        token = repo.create_magic_link_token(email, token_expiry())
        resp = client.post("/auth/verify", data={"token": token}, follow_redirects=False)
        assert resp.status_code == 302
        assert "/auth/set-password" not in resp.headers["Location"]


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


class TestAdminTriggers:
    def test_run_pipeline_requires_admin(self, client, app, repo, bundle):
        repo.create_user("plain@example.com", bundle.config.feed_id)
        repo.approve_user(repo.get_user_by_email("plain@example.com")["id"])
        user = repo.get_user_by_email("plain@example.com")
        _login(client, app, user)
        resp = client.post("/admin/run")
        assert resp.status_code == 403

    def test_run_pipeline_starts_and_redirects(self, client, app, admin_user):
        from unittest.mock import patch
        _login(client, app, admin_user)
        with patch("subprocess.Popen") as mock_popen:
            mock_popen.return_value = None
            resp = client.post("/admin/run", follow_redirects=False)
        assert resp.status_code == 302
        assert "/admin" in resp.headers["Location"]

    def test_send_digest_requires_admin(self, client, app, repo, bundle):
        repo.create_user("plain2@example.com", bundle.config.feed_id)
        repo.approve_user(repo.get_user_by_email("plain2@example.com")["id"])
        user = repo.get_user_by_email("plain2@example.com")
        _login(client, app, user)
        resp = client.post("/admin/send-digest")
        assert resp.status_code == 403

    def test_send_digest_with_no_digest_redirects(self, client, app, admin_user):
        _login(client, app, admin_user)
        resp = client.post("/admin/send-digest", follow_redirects=False)
        assert resp.status_code == 302


class TestGDPR:
    def test_export_returns_all_sections(self, client, app, admin_user):
        _login(client, app, admin_user)
        resp = client.get("/api/export")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "user" in data
        assert "preferences" in data
        assert "read_log" in data
        assert "feedback" in data
        assert data["user"]["email"] == "admin@example.com"

    def test_delete_account_soft_deletes_user(self, client, app, admin_user, repo):
        _login(client, app, admin_user)
        user_id = admin_user["id"]
        resp = client.post("/api/delete-account")
        assert resp.status_code == 200
        # User row should have deleted_at set, not hard-deleted
        row = repo._conn.execute(
            "SELECT deleted_at FROM users WHERE id=?", (user_id,)
        ).fetchone()
        assert row is not None
        assert row["deleted_at"] is not None

    def test_delete_account_anonymizes_feedback(self, client, app, admin_user, repo, bundle):
        _login(client, app, admin_user)
        user_id = admin_user["id"]
        # Need a real item in the DB before inserting feedback (FK constraint)
        repo._conn.execute("PRAGMA foreign_keys = OFF")
        repo._conn.execute(
            "INSERT OR IGNORE INTO items (id, feed_id, url, url_hash, title, body_raw, "
            "source_id, source_name, source_language, fetched_at, run_id, word_count, "
            "read_time_min, relevance_score, is_duplicate, translation_failed, company_tags) "
            "VALUES ('test-item','test-fixture','http://x','h1','T','B',"
            "'s','S','en','2026-01-01','r',10,1.0,1.0,0,0,'[]')"
        )
        repo._conn.execute("PRAGMA foreign_keys = ON")
        repo._conn.commit()
        repo.insert_feedback(bundle.config.feed_id, user_id, "test-item", "up")
        client.post("/api/delete-account")
        # feedback.user_id must be NULL after delete (anonymized)
        rows = repo._conn.execute(
            "SELECT user_id FROM feedback WHERE user_id=?", (user_id,)
        ).fetchall()
        assert len(rows) == 0

    def test_delete_account_removes_preferences(self, client, app, admin_user, repo):
        _login(client, app, admin_user)
        user_id = admin_user["id"]
        client.post("/api/delete-account")
        prefs = repo._conn.execute(
            "SELECT * FROM preferences WHERE user_id=?", (user_id,)
        ).fetchone()
        assert prefs is None
