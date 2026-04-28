"""Integration tests for CLI commands (M6)."""
from __future__ import annotations

import json
import os

import pytest
from click.testing import CliRunner

from cli import cli


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def feed_dir():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "../../feeds/test-fixture"))


class TestAdminPromote:
    def test_promote_creates_admin_user(self, runner, feed_dir, tmp_path):
        db = str(tmp_path / "test.db")
        result = runner.invoke(cli, [
            "admin", "promote",
            "--email", "boss@example.com",
            "--feed-dir", feed_dir,
            "--db-path", db,
        ])
        assert result.exit_code == 0, result.output
        assert "boss@example.com" in result.output

        from niche.core.models.repository import Repository
        repo = Repository(db)
        user = repo.get_user_by_email("boss@example.com")
        assert user is not None
        assert user["is_admin"] == 1
        assert user["is_approved"] == 1
        repo.close()

    def test_promote_idempotent(self, runner, feed_dir, tmp_path):
        db = str(tmp_path / "test.db")
        args = ["admin", "promote", "--email", "boss@example.com",
                "--feed-dir", feed_dir, "--db-path", db]
        r1 = runner.invoke(cli, args)
        r2 = runner.invoke(cli, args)
        assert r1.exit_code == 0
        assert r2.exit_code == 0

        from niche.core.models.repository import Repository
        repo = Repository(db)
        user = repo.get_user_by_email("boss@example.com")
        assert user["is_admin"] == 1
        repo.close()


class TestBundleValidate:
    def test_validate_test_fixture(self, runner, feed_dir):
        result = runner.invoke(cli, ["bundle", "validate", "--feed-dir", feed_dir])
        assert result.exit_code == 0
        assert "OK" in result.output

    def test_validate_missing_dir_fails(self, runner, tmp_path):
        result = runner.invoke(cli, ["bundle", "validate", "--feed-dir", str(tmp_path / "nonexistent")])
        assert result.exit_code != 0
