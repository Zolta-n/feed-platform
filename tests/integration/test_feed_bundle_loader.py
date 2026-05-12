"""Integration tests for the feed bundle loader."""
import os
import pytest
from niche.core.bundle_loader import load_bundle, BundleValidationError
from niche.core.sources.factory import SOURCE_REGISTRY

TEST_FEED_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../feeds/test-fixture")
)


def test_load_test_fixture_bundle():
    bundle = load_bundle(TEST_FEED_DIR)
    assert bundle.config.feed_id == "test-fixture"
    assert bundle.taxonomy is not None
    assert len(bundle.sources) > 0


def test_all_source_types_registered():
    bundle = load_bundle(TEST_FEED_DIR)
    for src in bundle.sources:
        assert src.source_type in SOURCE_REGISTRY, \
            f"Source type '{src.source_type}' not in SOURCE_REGISTRY"


def test_brake_by_wire_bundle_not_loaded_in_ci():
    """The test suite must run without loading the brake-by-wire bundle (EP10)."""
    import sys
    for module in list(sys.modules.keys()):
        if "brake-by-wire" in str(module) or "brake_by_wire" in str(module):
            pytest.fail(
                f"brake-by-wire bundle was loaded in test suite (EP10 violation): {module}"
            )


def test_prompts_have_correct_front_matter():
    bundle = load_bundle(TEST_FEED_DIR)
    for name, prompt in bundle.prompts.items():
        assert prompt.name == name, f"Prompt name mismatch: {name!r} vs {prompt.name!r}"
        assert prompt.version >= 1
        assert prompt.model
        assert prompt.last_updated
