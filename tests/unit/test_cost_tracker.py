"""Unit tests for the cost tracker."""
import pytest
from niche.core.cost.tracker import CostTracker, CostCapExceededError, _compute_usd


def test_compute_usd_haiku():
    usd = _compute_usd("claude-haiku-4-5", 1000, 100, 0, 0)
    assert usd > 0
    assert usd < 0.01  # Haiku is cheap


def test_compute_usd_cache_read_cheaper():
    base = _compute_usd("claude-haiku-4-5", 1000, 0, 0, 0)
    cached = _compute_usd("claude-haiku-4-5", 0, 0, 1000, 0)
    assert cached < base


def test_record_writes_to_db(repo):
    tracker = CostTracker(repo, "test-feed", run_id="run-1", daily_cap=5.0)
    usd = tracker.record(
        agent="summarizer",
        model="claude-haiku-4-5",
        input_tokens=1000,
        output_tokens=100,
    )
    assert usd > 0
    assert tracker.run_total > 0

    with repo.connect() as conn:
        entries = repo.get_cost_log(conn, "test-feed", run_id="run-1")
    assert len(entries) == 1
    assert entries[0]["agent"] == "summarizer"
    assert entries[0]["model"] == "claude-haiku-4-5"


def test_daily_cap_exceeded_raises(repo):
    tracker = CostTracker(repo, "test-feed", run_id="run-2", daily_cap=0.0)
    with pytest.raises(CostCapExceededError):
        tracker.record(
            agent="summarizer",
            model="claude-haiku-4-5",
            input_tokens=10000,
            output_tokens=1000,
        )


def test_monthly_cap_check(repo):
    tracker = CostTracker(repo, "test-feed", monthly_cap=0.0)
    # Insert a cost entry to exceed cap
    from niche.core.models.types import LlmCostEntry
    from datetime import datetime, timezone
    import uuid
    entry = LlmCostEntry(
        id=str(uuid.uuid4()),
        feed_id="test-feed",
        agent="classifier",
        model="claude-haiku-4-5",
        called_at=datetime.now(timezone.utc).isoformat(),
        usd=0.001,
    )
    with repo.connect() as conn:
        repo.insert_cost_entry(conn, entry)

    with pytest.raises(CostCapExceededError):
        tracker.check_monthly_cap()
