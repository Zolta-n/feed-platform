from __future__ import annotations

import os
import tempfile

import pytest

FEED_DIR = os.path.join(os.path.dirname(__file__), "..", "feeds", "test-fixture")


@pytest.fixture(scope="session")
def feed_dir() -> str:
    return os.path.abspath(FEED_DIR)


@pytest.fixture
def db_path(tmp_path) -> str:
    return str(tmp_path / "test.db")


@pytest.fixture
def bundle(feed_dir):
    from niche.core.bundle_loader import load_bundle
    return load_bundle(feed_dir)


@pytest.fixture
def repo(db_path):
    from niche.core.models.repository import Repository
    r = Repository(db_path)
    r.create_schema()
    yield r
    r.close()
