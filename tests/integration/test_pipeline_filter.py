"""Integration tests for the feed-level filter stage."""
from __future__ import annotations

import json
import os
import shutil

import pytest

from niche.core.bundle_loader import load_bundle


@pytest.fixture
def fixture_with_filters(tmp_path, feed_dir):
    """Copy feeds/test-fixture/ to tmp_path and add a synthetic filters.yaml."""
    dst = tmp_path / "fixture-with-filters"
    shutil.copytree(feed_dir, dst)
    (dst / "filters.yaml").write_text(
        "version: 1\n"
        "require_any:\n"
        "  match_fields: [title, body]\n"
        "  phrases: [brake, braking]\n"
        "block:\n"
        "  match_fields: [title]\n"
        "  phrases: [transit bus, lorry]\n"
    )
    return str(dst)


def test_bundle_loader_reads_filters_when_present(fixture_with_filters):
    bundle = load_bundle(fixture_with_filters)
    assert bundle.filters is not None
    assert bundle.filters.block is not None
    assert bundle.filters.require_any is not None
    assert bundle.filters.block.phrases == ("transit bus", "lorry")
    assert bundle.filters.require_any.match_fields == ("title", "body")


def test_bundle_loader_returns_none_filters_when_absent(feed_dir):
    """EP10: test-fixture has no filters.yaml — loader returns None, no crash."""
    bundle = load_bundle(feed_dir)
    assert bundle.filters is None


def test_runner_persists_filter_stats(tmp_path, fixture_with_filters):
    """End-to-end: pipeline run with filters writes filter_stats JSON to pipeline_runs."""
    from niche.core.models.repository import Repository
    from niche.core.pipeline.runner import run_pipeline

    # Need ANTHROPIC_API_KEY unset so the run uses stub mode end-to-end
    os.environ.pop("ANTHROPIC_API_KEY", None)

    db_path = str(tmp_path / "test.db")
    repo = Repository(db_path)
    repo.create_schema()
    bundle = load_bundle(fixture_with_filters)

    run_id = "test-run-1"
    run_pipeline(bundle, repo, run_id)

    row = repo._conn.execute(
        "SELECT filter_stats FROM pipeline_runs WHERE id=?", (run_id,)
    ).fetchone()
    repo.close()

    assert row is not None
    if row["filter_stats"]:
        stats = json.loads(row["filter_stats"])
        assert "blocked" in stats
        assert "require_missed" in stats
        assert "samples" in stats
