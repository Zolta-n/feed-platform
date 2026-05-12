from __future__ import annotations

import pytest

from niche.core.cost.tracker import (
    CostCapExceededError,
    check_daily_cap,
    cost_usd,
    record_call,
)


def test_cost_usd_haiku_input_only():
    usd = cost_usd("claude-haiku-4-5", input_tokens=1_000_000, output_tokens=0)
    assert usd == pytest.approx(1.00, rel=1e-6)


def test_cost_usd_haiku_output_only():
    usd = cost_usd("claude-haiku-4-5", input_tokens=0, output_tokens=1_000_000)
    assert usd == pytest.approx(5.00, rel=1e-6)


def test_cost_usd_cache_read_cheaper_than_input():
    usd_input = cost_usd("claude-haiku-4-5", input_tokens=1000, output_tokens=0)
    usd_cache = cost_usd("claude-haiku-4-5", input_tokens=0, output_tokens=0, cache_read_tokens=1000)
    assert usd_cache < usd_input


def test_cost_usd_cache_write_more_than_input():
    usd_input = cost_usd("claude-haiku-4-5", input_tokens=1000, output_tokens=0)
    usd_write = cost_usd("claude-haiku-4-5", input_tokens=0, output_tokens=0, cache_write_tokens=1000)
    assert usd_write > usd_input


def test_cost_usd_unknown_model_uses_default():
    # Should not raise; falls back to Haiku pricing
    usd = cost_usd("some-unknown-model", input_tokens=1_000_000, output_tokens=0)
    assert usd > 0


def test_record_call_inserts_row(repo):
    usd = record_call(
        repo,
        feed_id="test-fixture",
        run_id="run-001",
        agent="classify",
        model="claude-haiku-4-5",
        prompt_name="classify-topic",
        prompt_version=1,
        input_tokens=100,
        output_tokens=20,
        cache_read_tokens=50,
        cache_write_tokens=0,
    )
    assert usd > 0
    total = repo.get_daily_cost_usd("test-fixture")
    assert total == pytest.approx(usd, rel=1e-6)


def test_record_call_accumulates(repo):
    record_call(
        repo,
        feed_id="test-fixture",
        run_id="run-001",
        agent="classify",
        model="claude-haiku-4-5",
        prompt_name="classify-topic",
        prompt_version=1,
        input_tokens=100,
        output_tokens=10,
    )
    record_call(
        repo,
        feed_id="test-fixture",
        run_id="run-001",
        agent="classify",
        model="claude-haiku-4-5",
        prompt_name="classify-item-type",
        prompt_version=1,
        input_tokens=80,
        output_tokens=8,
    )
    total = repo.get_daily_cost_usd("test-fixture")
    expected = (
        cost_usd("claude-haiku-4-5", 100, 10)
        + cost_usd("claude-haiku-4-5", 80, 8)
    )
    assert total == pytest.approx(expected, rel=1e-6)


def test_check_daily_cap_not_exceeded(repo):
    # No spend yet — should not raise
    check_daily_cap(repo, "test-fixture", cap_usd=1.0)


def test_check_daily_cap_exceeded(repo):
    record_call(
        repo,
        feed_id="test-fixture",
        run_id="run-001",
        agent="classify",
        model="claude-haiku-4-5",
        prompt_name="classify-topic",
        prompt_version=1,
        input_tokens=1_000_000,
        output_tokens=200_000,
    )
    with pytest.raises(CostCapExceededError):
        check_daily_cap(repo, "test-fixture", cap_usd=0.001)


def test_check_daily_cap_isolated_by_feed(repo):
    record_call(
        repo,
        feed_id="other-feed",
        run_id="run-001",
        agent="classify",
        model="claude-haiku-4-5",
        prompt_name="classify-topic",
        prompt_version=1,
        input_tokens=1_000_000,
        output_tokens=200_000,
    )
    # test-fixture has no spend — should not raise
    check_daily_cap(repo, "test-fixture", cap_usd=0.001)


def test_get_run_total_usd_sums_calls_for_one_run(repo):
    record_call(
        repo,
        feed_id="test-fixture",
        run_id="run-A",
        agent="classify",
        model="claude-haiku-4-5",
        prompt_name="classify-topic",
        prompt_version=1,
        input_tokens=100,
        output_tokens=10,
    )
    record_call(
        repo,
        feed_id="test-fixture",
        run_id="run-A",
        agent="summarize",
        model="claude-haiku-4-5",
        prompt_name="summarize",
        prompt_version=1,
        input_tokens=200,
        output_tokens=50,
    )
    expected = (
        cost_usd("claude-haiku-4-5", 100, 10)
        + cost_usd("claude-haiku-4-5", 200, 50)
    )
    assert repo.get_run_total_usd("run-A") == pytest.approx(expected, rel=1e-6)


def test_get_run_total_usd_isolates_by_run_id(repo):
    record_call(
        repo,
        feed_id="test-fixture",
        run_id="run-A",
        agent="classify",
        model="claude-haiku-4-5",
        prompt_name="classify-topic",
        prompt_version=1,
        input_tokens=100,
        output_tokens=10,
    )
    assert repo.get_run_total_usd("run-B") == 0.0


def test_get_run_total_usd_no_calls_returns_zero(repo):
    assert repo.get_run_total_usd("never-existed") == 0.0
