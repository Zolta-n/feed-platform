"""Unit tests for the feed bundle loader."""
import os
import tempfile
import textwrap
import pytest

from niche.core.bundle_loader import BundleValidationError, load_bundle


TEST_FEED_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../feeds/test-fixture")
)


def test_load_test_fixture():
    bundle = load_bundle(TEST_FEED_DIR)
    assert bundle.config.feed_id == "test-fixture"
    assert bundle.config.name == "TestFeed"
    assert len(bundle.taxonomy.topics) > 0
    assert len(bundle.taxonomy.regions) > 0
    assert len(bundle.sources) > 0
    assert len(bundle.watchlist) > 0


def test_bundle_has_required_topic_ids():
    bundle = load_bundle(TEST_FEED_DIR)
    topic_ids = {t.id for t in bundle.taxonomy.topics}
    for required in ("tier1", "oem", "regulation", "technology"):
        assert required in topic_ids


def test_bundle_watchlist_has_synthetic_names():
    """Watchlist must use obviously-synthetic names (EP10)."""
    bundle = load_bundle(TEST_FEED_DIR)
    for entry in bundle.watchlist:
        # Should contain AcmeBrake or FakeTier1Co or similar synthetic names
        assert any(
            word in entry.name for word in
            ["Acme", "Fake", "Stub", "Synthetic", "Test"]
        ), f"Watchlist entry '{entry.name}' doesn't look synthetic"


def test_missing_required_key_raises():
    with tempfile.TemporaryDirectory() as d:
        # Create a valid structure but with missing feed_id
        os.makedirs(os.path.join(d, "bad-bundle", "prompts"))
        bad_dir = os.path.join(d, "bad-bundle")
        with open(os.path.join(bad_dir, "config.yaml"), "w") as f:
            f.write("name: Missing\n")  # missing feed_id
        with open(os.path.join(bad_dir, "taxonomy.yaml"), "w") as f:
            f.write("topics: []\nregions: []\nitem_types: []\nnav_tabs: []\n")
        with open(os.path.join(bad_dir, "sources.yaml"), "w") as f:
            f.write("sources: []\n")
        with open(os.path.join(bad_dir, "watchlist.yaml"), "w") as f:
            f.write("companies: []\n")
        with pytest.raises(BundleValidationError, match="feed_id"):
            load_bundle(bad_dir)


def test_feed_id_must_match_directory_name():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "wrong-name", "prompts"))
        bad_dir = os.path.join(d, "wrong-name")
        with open(os.path.join(bad_dir, "config.yaml"), "w") as f:
            f.write("feed_id: correct-name\nname: Test\n")
        with open(os.path.join(bad_dir, "taxonomy.yaml"), "w") as f:
            f.write("topics: []\nregions: []\nitem_types: []\nnav_tabs: []\n")
        with open(os.path.join(bad_dir, "sources.yaml"), "w") as f:
            f.write("sources: []\n")
        with open(os.path.join(bad_dir, "watchlist.yaml"), "w") as f:
            f.write("companies: []\n")
        with pytest.raises(BundleValidationError, match="directory name"):
            load_bundle(bad_dir)


def test_prompts_loaded():
    bundle = load_bundle(TEST_FEED_DIR)
    # test-fixture should have at least summarize prompt
    assert "summarize" in bundle.prompts
    pm = bundle.prompts["summarize"]
    assert pm.version >= 1
    assert pm.model.startswith("claude")
    assert len(pm.body) > 0
