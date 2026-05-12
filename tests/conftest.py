"""
Pytest configuration — loads test-fixture feed; never brake-by-wire (EP10).
"""
import os
import tempfile

import pytest

TEST_FEED_DIR = os.path.join(
    os.path.dirname(__file__), "..", "feeds", "test-fixture"
)


@pytest.fixture(scope="session")
def test_feed_dir():
    return os.path.abspath(TEST_FEED_DIR)


@pytest.fixture(scope="session")
def bundle(test_feed_dir):
    from niche.core.bundle_loader import load_bundle
    return load_bundle(test_feed_dir)


@pytest.fixture
def tmp_db():
    """Provide a temporary SQLite database path that is deleted after the test."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    from niche.core.models.schema import init_db
    init_db(db_path)
    yield db_path
    os.unlink(db_path)


@pytest.fixture
def repo(tmp_db):
    from niche.core.models.repository import Repository
    return Repository(tmp_db)


@pytest.fixture
def app(tmp_db, test_feed_dir):
    """Flask test app configured with test-fixture feed."""
    from niche.web.app import create_app
    app = create_app({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "DB_PATH": tmp_db,
        "FEED_DIR": test_feed_dir,
        "SESSION_SECRET": "test-secret",
        "SCHEDULER_ENABLED": False,
    })
    return app


@pytest.fixture
def client(app):
    return app.test_client()
