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


def test_bundle_loader_parses_max_age_days(tmp_path, feed_dir):
    """max_age_days is parsed off the top-level of filters.yaml."""
    import shutil
    dst = tmp_path / "fixture-with-age"
    shutil.copytree(feed_dir, dst)
    (dst / "filters.yaml").write_text(
        "version: 1\n"
        "max_age_days: 30\n"
        "require_any:\n"
        "  match_fields: [title, body]\n"
        "  phrases: [brake]\n"
    )
    bundle = load_bundle(str(dst))
    assert bundle.filters is not None
    assert bundle.filters.max_age_days == 30


def test_bundle_loader_rejects_invalid_max_age_days(tmp_path, feed_dir):
    import shutil
    from niche.core.bundle_loader import BundleValidationError
    dst = tmp_path / "fixture-bad-age"
    shutil.copytree(feed_dir, dst)
    (dst / "filters.yaml").write_text(
        "version: 1\n"
        "max_age_days: -5\n"
    )
    with pytest.raises(BundleValidationError):
        load_bundle(str(dst))


def test_rolling_pool_filters_stale_items(tmp_path, fixture_with_filters):
    """A stale Item already in the DB that matches a block phrase must not reach the digest."""
    from datetime import datetime, timezone
    from niche.core.models.repository import Repository
    from niche.core.pipeline.filter_relevance import filter_items
    from niche.core.models.types import Item

    db_path = str(tmp_path / "pool.db")
    repo = Repository(db_path)
    repo.create_schema()
    bundle = load_bundle(fixture_with_filters)

    # Seed FK targets: a source and a pipeline_run row.
    repo.upsert_source({
        "id": "src", "feed_id": bundle.config.feed_id, "source_type": "stub",
        "url": None, "name": "stub", "default_region": None, "default_topic": None,
        "source_weight": 1.0, "enabled": 1, "added_by": "test",
    })
    repo.insert_pipeline_run("old-run", bundle.config.feed_id,
                             datetime.now(timezone.utc).isoformat())

    # Seed a "stale" item directly — the kind that would have been
    # classified before filters existed: a transit-bus article.
    stale = Item(
        id="stale-1", feed_id=bundle.config.feed_id,
        url="https://example.invalid/stale", url_hash="h-stale", title_hash="t-stale",
        title="New transit bus brake retrofit",
        title_translated="New transit bus brake retrofit",
        body_raw="Body about transit bus rear axle brakes",
        body_translated="Body about transit bus rear axle brakes",
        summary="Stub summary", why_it_matters="Stub why",
        source_id="src", source_name="src", source_language="en",
        topic_tag="tier1", item_type="report", region_tag="europe",
        company_tags=[], translation_failed=False, translation_provider=None,
        relevance_score=1.0, published_at=None,
        fetched_at=datetime.now(timezone.utc),
        run_id="old-run", word_count=10, read_time_min=0.1,
        is_duplicate=False, duplicate_of=None,
    )
    repo.insert_items([stale])

    # Build a pool that includes the stale item, then apply filter_items
    pool = repo.get_recent_pool_items(bundle.config.feed_id, days=2)
    assert any(i.id == "stale-1" for i in pool), "stale item should be in the pool pre-filter"

    survivors, stats = filter_items(pool, bundle.filters)
    assert all(i.id != "stale-1" for i in survivors), "stale block-match must be dropped"
    assert stats["blocked"] >= 1
    repo.close()
