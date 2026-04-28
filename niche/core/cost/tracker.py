from __future__ import annotations

_PRICING: dict[str, dict[str, float]] = {
    "claude-haiku-4-5": {
        "input": 1.00 / 1_000_000,
        "output": 5.00 / 1_000_000,
        "cache_write": 1.25 / 1_000_000,
        "cache_read": 0.10 / 1_000_000,
    },
    "claude-sonnet-4-6": {
        "input": 3.00 / 1_000_000,
        "output": 15.00 / 1_000_000,
        "cache_write": 3.75 / 1_000_000,
        "cache_read": 0.30 / 1_000_000,
    },
}

_DEFAULT_PRICING = _PRICING["claude-haiku-4-5"]


class CostCapExceededError(Exception):
    pass


def cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    p = _PRICING.get(model, _DEFAULT_PRICING)
    return (
        input_tokens * p["input"]
        + output_tokens * p["output"]
        + cache_read_tokens * p["cache_read"]
        + cache_write_tokens * p["cache_write"]
    )


def record_call(
    repo,
    *,
    feed_id: str,
    run_id: str | None,
    agent: str,
    model: str,
    prompt_name: str | None,
    prompt_version: int | None,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    usd = cost_usd(model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens)
    repo.insert_llm_cost(
        feed_id=feed_id,
        run_id=run_id,
        agent=agent,
        model=model,
        prompt_name=prompt_name,
        prompt_version=prompt_version,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_read_tokens=cache_read_tokens,
        cache_write_tokens=cache_write_tokens,
        usd=usd,
    )
    return usd


def check_daily_cap(repo, feed_id: str, cap_usd: float) -> None:
    total = repo.get_daily_cost_usd(feed_id)
    if total >= cap_usd:
        raise CostCapExceededError(
            f"Daily LLM cost cap of ${cap_usd:.4f} exceeded "
            f"(current: ${total:.4f}) for feed {feed_id!r}"
        )
