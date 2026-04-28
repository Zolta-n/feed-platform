from __future__ import annotations

import os
import shutil
import tempfile

import pytest
import yaml

from niche.core.bundle_loader import BundleValidationError, load_bundle


def _copy_fixture(tmp_path: str) -> str:
    src = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../feeds/test-fixture"))
    dst = os.path.join(tmp_path, "test-fixture")
    shutil.copytree(src, dst)
    return dst


def test_valid_bundle_loads(feed_dir):
    bundle = load_bundle(feed_dir)
    assert bundle.config.feed_id == "test-fixture"
    assert bundle.config.name == "TestFeed"
    assert len(bundle.taxonomy.topics) >= 1
    assert len(bundle.taxonomy.regions) >= 1
    assert len(bundle.sources) >= 1
    assert len(bundle.companies) >= 1
    assert "summarize" in bundle.prompts
    assert "classify-topic" in bundle.prompts
    assert "classify-item-type" in bundle.prompts
    assert "why-it-matters" in bundle.prompts
    assert "translate" in bundle.prompts


def test_missing_feed_id_raises(tmp_path):
    dst = _copy_fixture(str(tmp_path))
    config_path = os.path.join(dst, "config.yaml")
    with open(config_path) as f:
        data = yaml.safe_load(f)
    del data["feed_id"]
    with open(config_path, "w") as f:
        yaml.dump(data, f)

    with pytest.raises(BundleValidationError, match="feed_id"):
        load_bundle(dst)


def test_missing_prompt_raises(tmp_path):
    dst = _copy_fixture(str(tmp_path))
    os.remove(os.path.join(dst, "prompts", "summarize.md"))

    with pytest.raises(BundleValidationError, match="summarize"):
        load_bundle(dst)


def test_feed_id_matches_dirname(tmp_path):
    dst = _copy_fixture(str(tmp_path))
    config_path = os.path.join(dst, "config.yaml")
    with open(config_path) as f:
        data = yaml.safe_load(f)
    data["feed_id"] = "wrong-id"
    with open(config_path, "w") as f:
        yaml.dump(data, f)

    from niche.core.bundle_loader import validate_bundle
    with pytest.raises(BundleValidationError, match="does not match directory"):
        validate_bundle(dst)


def test_bundle_is_frozen(feed_dir):
    bundle = load_bundle(feed_dir)
    with pytest.raises((AttributeError, TypeError)):
        bundle.config.feed_id = "mutated"  # type: ignore[misc]
