"""
LLM cost tracker — logs every API call and enforces daily/monthly caps.

Usage:
    tracker = CostTracker(repo, feed_id, run_id, daily_cap=1.00, monthly_cap=18.00)
    tracker.record(agent="summarizer", model="claude-haiku-4-5", ...)
"""
from __future__ import annotations

import datetime
import logging
import uuid
from typing import Optional

from ..models.repository import Repository
from ..models.types import LlmCostEntry

logger = logging.getLogger(__name__)

# Static price table (USD per token) — update when Anthropic adjusts pricing
PRICING: dict[str, dict[str, float]] = {
    "claude-haiku-4-5": {
        "input": 0.00000080,       # $0.80 / 1M input tokens
        "output": 0.00000400,      # $4.00 / 1M output tokens
        "cache_read": 0.000000080, # 10% of input rate
        "cache_write": 0.00000100, # $1.00 / 1M tokens
    },
    "claude-sonnet-4-6": {
        "input": 0.00000300,
        "output": 0.00001500,
        "cache_read": 0.000000300,
        "cache_write": 0.00000375,
    },
    "deepl": {
        "input": 0.0,  # free tier; tracked for auditability
        "output": 0.0,
        "cache_read": 0.0,
        "cache_write": 0.0,
    },
}


class CostCapExceededError(Exception):
    """Raised when a pipeline run would exceed the configured daily cost cap."""


def _compute_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int,
    cache_write_tokens: int,
) -> float:
    rates = PRICING.get(model, PRICING["claude-haiku-4-5"])
    return (
        input_tokens * rates["input"]
        + output_tokens * rates["output"]
        + cache_read_tokens * rates["cache_read"]
        + cache_write_tokens * rates["cache_write"]
    )


class CostTracker:
    def __init__(
        self,
        repo: Repository,
        feed_id: str,
        run_id: Optional[str] = None,
        daily_cap: float = 1.00,
        monthly_cap: float = 18.00,
    ) -> None:
        self.repo = repo
        self.feed_id = feed_id
        self.run_id = run_id
        self.daily_cap = daily_cap
        self.monthly_cap = monthly_cap
        self._run_total: float = 0.0

    def check_monthly_cap(self) -> None:
        """Call at pipeline start. Raises CostCapExceededError if over monthly budget."""
        year_month = datetime.date.today().strftime("%Y-%m")
        with self.repo.connect() as conn:
            monthly_total = self.repo.get_cost_for_month(
                conn, self.feed_id, year_month
            )
        if monthly_total >= self.monthly_cap:
            raise CostCapExceededError(
                f"Monthly cost cap ${self.monthly_cap:.2f} exceeded "
                f"(current: ${monthly_total:.4f}). Pipeline aborted."
            )

    def record(
        self,
        agent: str,
        model: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
        prompt_name: Optional[str] = None,
        prompt_version: Optional[int] = None,
    ) -> float:
        """Log a single LLM call. Returns cost in USD. Raises if daily cap exceeded."""
        usd = _compute_usd(
            model, input_tokens, output_tokens,
            cache_read_tokens, cache_write_tokens
        )
        self._run_total += usd

        if self._run_total > self.daily_cap:
            raise CostCapExceededError(
                f"Daily cost cap ${self.daily_cap:.2f} exceeded "
                f"(run total: ${self._run_total:.4f}). Pipeline aborted."
            )

        entry = LlmCostEntry(
            id=str(uuid.uuid4()),
            feed_id=self.feed_id,
            run_id=self.run_id,
            agent=agent,
            model=model,
            prompt_name=prompt_name,
            prompt_version=prompt_version,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            usd=usd,
            called_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )
        with self.repo.connect() as conn:
            self.repo.insert_cost_entry(conn, entry)

        logger.debug(
            "Cost: %s/%s $%.6f (run_total: $%.4f)",
            agent, model, usd, self._run_total,
        )
        return usd

    @property
    def run_total(self) -> float:
        return self._run_total
