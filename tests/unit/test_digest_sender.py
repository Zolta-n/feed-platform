"""Unit tests for the email digest sender (M6)."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _make_digest_row(email_sent_at=None, item_ids=None, cluster_map=None):
    row = MagicMock()
    row.__getitem__ = lambda self, key: {
        "id": "d1",
        "date": "2026-04-28",
        "item_count": 2,
        "total_read_time_min": 4.0,
        "email_sent_at": email_sent_at,
        "item_ids": json.dumps(item_ids or ["i1", "i2"]),
        "cluster_map": json.dumps(cluster_map or []),
    }[key]
    return row


def _make_user(uid="u1", approved=1, email_enabled=1, deleted_at=None):
    row = MagicMock()
    row.__getitem__ = lambda self, key: {
        "id": uid,
        "email": f"{uid}@example.com",
        "is_approved": approved,
        "email_enabled": email_enabled,
        "deleted_at": deleted_at,
    }[key]
    return row


def _make_item(iid="i1"):
    return {
        "id": iid,
        "url": f"https://example.com/{iid}",
        "title": f"Title {iid}",
        "title_translated": None,
        "source_name": "Test Source",
        "published_at": "2026-04-28T10:00:00",
        "read_time_min": 2,
        "topic_tag": "technology",
        "summary": "A test summary.",
        "why_it_matters": "It matters because.",
    }


class TestSendDigest:
    def _make_bundle_and_repo(self, users, items, email_sent_at=None):
        bundle = MagicMock()
        bundle.config.feed_id = "test-fixture"
        bundle.config.name = "TestFeed"
        bundle.config.tagline = "Test tagline"
        bundle.config.accent_color = "#123456"
        bundle.config.from_email = "noreply@example.invalid"

        repo = MagicMock()
        repo.get_latest_digest.return_value = _make_digest_row(
            email_sent_at=email_sent_at,
            item_ids=[i["id"] for i in items],
        )
        repo.get_items_by_ids.return_value = items
        repo.get_all_users.return_value = users
        repo._conn = MagicMock()

        return bundle, repo

    def test_no_digest_returns_zero(self):
        from niche.core.email.digest_sender import send_digest
        bundle = MagicMock()
        bundle.config.feed_id = "test-fixture"
        repo = MagicMock()
        repo.get_latest_digest.return_value = None
        assert send_digest(bundle, repo, MagicMock(), "http://localhost") == 0

    def test_already_sent_skips(self):
        from niche.core.email.digest_sender import send_digest
        bundle, repo = self._make_bundle_and_repo(
            users=[_make_user()],
            items=[_make_item()],
            email_sent_at="2026-04-28T06:00:00",
        )
        provider = MagicMock()
        assert send_digest(bundle, repo, provider, "http://localhost") == 0
        provider.send.assert_not_called()

    def test_no_eligible_users_returns_zero(self):
        from niche.core.email.digest_sender import send_digest
        bundle, repo = self._make_bundle_and_repo(
            users=[_make_user(approved=0)],
            items=[_make_item()],
        )
        provider = MagicMock()
        assert send_digest(bundle, repo, provider, "http://localhost") == 0
        provider.send.assert_not_called()

    def test_email_disabled_user_skipped(self):
        from niche.core.email.digest_sender import send_digest
        bundle, repo = self._make_bundle_and_repo(
            users=[_make_user(email_enabled=0)],
            items=[_make_item()],
        )
        provider = MagicMock()
        assert send_digest(bundle, repo, provider, "http://localhost") == 0
        provider.send.assert_not_called()

    def test_deleted_user_skipped(self):
        from niche.core.email.digest_sender import send_digest
        bundle, repo = self._make_bundle_and_repo(
            users=[_make_user(deleted_at="2026-04-27T00:00:00")],
            items=[_make_item()],
        )
        provider = MagicMock()
        assert send_digest(bundle, repo, provider, "http://localhost") == 0

    def test_sends_to_eligible_user_and_marks_sent(self):
        from niche.core.email.digest_sender import send_digest
        from flask import Flask
        app = Flask(__name__, template_folder="../../niche/web/templates")
        bundle, repo = self._make_bundle_and_repo(
            users=[_make_user()],
            items=[_make_item("i1"), _make_item("i2")],
        )
        provider = MagicMock()
        with app.app_context():
            with patch("flask.render_template", return_value="<html/>"):
                count = send_digest(bundle, repo, provider, "http://localhost")

        assert count == 1
        provider.send.assert_called_once()
        call_kwargs = provider.send.call_args.kwargs
        assert call_kwargs["to"] == "u1@example.com"
        assert "TestFeed" in call_kwargs["subject"]
        # email_sent_at should have been set
        repo._conn.execute.assert_called()
        repo._conn.commit.assert_called()

    def test_provider_failure_continues_to_next_user(self):
        from niche.core.email.digest_sender import send_digest
        from flask import Flask
        app = Flask(__name__, template_folder="../../niche/web/templates")
        bundle, repo = self._make_bundle_and_repo(
            users=[_make_user("u1"), _make_user("u2")],
            items=[_make_item()],
        )
        call_count = [0]

        def _failing_send(**kwargs):
            call_count[0] += 1
            if kwargs["to"] == "u1@example.com":
                raise RuntimeError("SMTP error")

        provider = MagicMock()
        provider.send.side_effect = _failing_send

        with app.app_context():
            with patch("flask.render_template", return_value="<html/>"):
                count = send_digest(bundle, repo, provider, "http://localhost")

        assert count == 1
        assert call_count[0] == 2

    def test_email_template_has_no_hardcoded_feed_strings(self):
        """EP1: email template must not contain domain-specific strings."""
        import os
        template_path = os.path.join(
            os.path.dirname(__file__), "../../niche/web/templates/email/digest.html"
        )
        content = open(template_path).read()
        forbidden = ["brake-by-wire", "BrakeCo", "AcmeBrake", "FakeTier1Co"]
        for word in forbidden:
            assert word not in content, f"Template contains hardcoded domain string: {word}"


class TestPruneReadLog:
    def test_prune_deletes_old_entries(self, tmp_path):
        from niche.core.models.repository import Repository
        db = str(tmp_path / "test.db")
        repo = Repository(db)
        repo.create_schema()

        old_ts = "2025-01-01T00:00:00+00:00"
        recent_ts = datetime.now(timezone.utc).isoformat()
        feed_id = "test-fixture"

        # Disable FK enforcement so we can insert test rows without parent records
        repo._conn.execute("PRAGMA foreign_keys = OFF")
        repo._conn.execute(
            "INSERT INTO read_log (id, user_id, item_id, feed_id, read_at) VALUES (?,?,?,?,?)",
            ("r1", "u1", "i1", feed_id, old_ts),
        )
        repo._conn.execute(
            "INSERT INTO read_log (id, user_id, item_id, feed_id, read_at) VALUES (?,?,?,?,?)",
            ("r2", "u1", "i2", feed_id, recent_ts),
        )
        repo._conn.commit()

        deleted = repo.prune_read_log(days=180)
        assert deleted == 1

        remaining = repo._conn.execute("SELECT id FROM read_log").fetchall()
        assert len(remaining) == 1
        assert remaining[0][0] == "r2"

        repo.close()
