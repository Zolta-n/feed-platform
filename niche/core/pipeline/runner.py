from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from niche.core.models.types import Digest, FeedBundle, Item
from niche.core.models.repository import Repository
from niche.core.pipeline.classify import classify
from niche.core.pipeline.cluster import cluster
from niche.core.pipeline.compose import _DIGEST_MIN_ITEMS, compose
from niche.core.pipeline.dedup import dedup, dedup_translated
from niche.core.pipeline.filter_relevance import filter_relevance
from niche.core.pipeline.rank import rank
from niche.core.pipeline.summarize import summarize
from niche.core.pipeline.translate import translate
from niche.core.sources.factory import build_sources

logger = logging.getLogger(__name__)


@dataclass
class StageResult:
    stage: str
    item_count_in: int
    item_count_out: int
    duration_s: float


_MAX_ITEMS_PER_RUN = 50  # cap LLM calls; first run on a new feed may have hundreds of new items


def _diverse_cap(items: list, bundle, cap: int) -> list:
    """Return up to `cap` items with proportional representation across sources.

    Each source contributes items in proportion to its source_weight; sources
    with fewer items are not penalised. This prevents a single high-volume
    source from filling the entire cap budget.
    """
    import math
    from collections import defaultdict

    source_weight_map = {s.id: s.source_weight for s in bundle.sources}
    buckets: dict[str, list] = defaultdict(list)
    for item in items:
        buckets[item.source_id].append(item)

    total_weight = sum(source_weight_map.get(sid, 1.0) for sid in buckets)
    # Allocate slots proportionally; each source gets at least 1 slot
    slots: dict[str, int] = {}
    remaining = cap
    for sid, bucket in buckets.items():
        w = source_weight_map.get(sid, 1.0)
        alloc = max(1, math.floor(cap * w / total_weight))
        slots[sid] = min(alloc, len(bucket))
        remaining -= slots[sid]

    # Distribute any leftover slots to the sources with the most items first
    if remaining > 0:
        for sid in sorted(buckets, key=lambda s: len(buckets[s]), reverse=True):
            extra = min(remaining, len(buckets[sid]) - slots[sid])
            if extra > 0:
                slots[sid] += extra
                remaining -= extra
            if remaining == 0:
                break

    result = []
    for sid, bucket in buckets.items():
        result.extend(bucket[:slots[sid]])
    return result


def run_pipeline(bundle: FeedBundle, repo: Repository, run_id: str) -> list[StageResult]:
    started_at = datetime.now(timezone.utc).isoformat()
    repo.insert_pipeline_run(run_id, bundle.config.feed_id, started_at)

    results: list[StageResult] = []
    total_usd = 0.0

    try:
        # Sync sources from bundle config into DB before any item inserts
        for src_cfg in bundle.sources:
            repo.upsert_source({
                "id": src_cfg.id,
                "feed_id": src_cfg.feed_id,
                "source_type": src_cfg.source_type,
                "url": src_cfg.url,
                "name": src_cfg.name,
                "default_region": src_cfg.default_region,
                "default_topic": src_cfg.default_topic,
                "source_weight": src_cfg.source_weight,
                "enabled": int(src_cfg.enabled),
                "added_by": "config",
            })

        # --- Fetch ---
        t0 = time.monotonic()
        sources = build_sources(list(bundle.sources), repo)
        raw_items = []
        for source in sources:
            fetched = source.fetch()
            raw_items.extend(fetched)
            logger.info("run_id=%s source=%s fetched=%d", run_id, source.source_id, len(fetched))
        results.append(StageResult("fetch", 0, len(raw_items), time.monotonic() - t0))
        repo.patch_pipeline_run(run_id, items_fetched=len(raw_items), current_stage="filter")

        # --- Filter (feed-level relevance) ---
        # Drops obviously off-topic items pre-LLM so we don't burn tokens
        # classifying / translating / summarizing junk. No-op if the feed
        # bundle has no filters.yaml.
        t0 = time.monotonic()
        pre_filter_count = len(raw_items)
        raw_items, filter_stats = filter_relevance(raw_items, bundle.filters)
        results.append(StageResult("filter", pre_filter_count, len(raw_items), time.monotonic() - t0))
        if filter_stats:
            import json as _json_filter
            repo.patch_pipeline_run(run_id, filter_stats=_json_filter.dumps(filter_stats))
        repo.patch_pipeline_run(run_id, current_stage="dedup")

        # --- Dedup ---
        t0 = time.monotonic()
        existing_hashes = repo.get_url_hashes(bundle.config.feed_id)
        existing_title_hashes = repo.get_title_hashes(bundle.config.feed_id)
        recent_titles = repo.get_recent_titles(bundle.config.feed_id)
        source_names = {s.id: s.name for s in bundle.sources}
        items = dedup(
            raw_items, existing_hashes, existing_title_hashes,
            recent_titles, bundle.config.feed_id, run_id, source_names,
        )
        repo.insert_items(items)
        non_dupes = [i for i in items if not i.is_duplicate]
        logger.info("run_id=%s dedup in=%d out=%d dupes=%d", run_id, len(items), len(non_dupes), len(items) - len(non_dupes))
        results.append(StageResult("dedup", len(raw_items), len(non_dupes), time.monotonic() - t0))
        repo.patch_pipeline_run(run_id, items_after_dedup=len(non_dupes), current_stage="classify")

        # Cap items sent to LLM stages to bound cost and latency per run.
        # Uses a round-robin across sources weighted by source_weight so no
        # single prolific source crowds out all others.
        if len(non_dupes) > _MAX_ITEMS_PER_RUN:
            non_dupes = _diverse_cap(non_dupes, bundle, _MAX_ITEMS_PER_RUN)
            logger.info("run_id=%s capped to %d items for LLM stages", run_id, len(non_dupes))

        # --- Classify ---
        t0 = time.monotonic()
        classified = classify(non_dupes, bundle, repo, run_id)
        repo.update_items(classified)
        logger.info("run_id=%s classify out=%d", run_id, len(classified))
        results.append(StageResult("classify", len(non_dupes), len(classified), time.monotonic() - t0))
        repo.patch_pipeline_run(run_id, current_stage="translate")

        # --- Translate ---
        t0 = time.monotonic()
        translated = translate(classified, bundle, repo, run_id)
        translated = dedup_translated(translated)
        cross_dupes = sum(1 for i in translated if i.is_duplicate)
        if cross_dupes:
            logger.info("run_id=%s cross-lang dedup removed %d near-duplicates", run_id, cross_dupes)
        repo.update_items(translated)
        translated = [i for i in translated if not i.is_duplicate]
        results.append(StageResult("translate", len(classified), len(translated), time.monotonic() - t0))
        repo.patch_pipeline_run(run_id, current_stage="summarize")

        # --- Summarize ---
        t0 = time.monotonic()
        summarized = summarize(translated, bundle, repo, run_id)
        repo.update_items(summarized)
        results.append(StageResult("summarize", len(translated), len(summarized), time.monotonic() - t0))
        repo.patch_pipeline_run(run_id, current_stage="rank")

        # --- Rank ---
        t0 = time.monotonic()
        ranked = rank(summarized, bundle, preferences={}, repo=repo)
        repo.update_items(ranked)
        results.append(StageResult("rank", len(summarized), len(ranked), time.monotonic() - t0))
        repo.patch_pipeline_run(run_id, current_stage="cluster")

        # --- Build rolling pool for cluster/compose ---
        # Merge today's new items with classified items from the past 2 days so
        # that running the pipeline multiple times doesn't overwrite a rich digest
        # with a thin one when the article pool is already depleted.
        import json as _json
        recent = repo.get_recent_pool_items(bundle.config.feed_id, days=2)
        current_ids = {item.id for item in ranked}
        pool = ranked + [item for item in recent if item.id not in current_ids]
        pool.sort(key=lambda i: i.relevance_score, reverse=True)
        # Second-pass cross-lang dedup on the merged pool catches near-duplicates
        # that slipped through when they were processed in separate pipeline runs.
        pool = [i for i in dedup_translated(pool) if not i.is_duplicate]

        # Prefer fresh content: move items already in the previous digest to the
        # back of the pool so new articles get priority in cluster/compose.
        prev_digest = repo.get_latest_digest(bundle.config.feed_id)
        prev_ids: set[str] = set()
        if prev_digest:
            try:
                prev_ids = set(_json.loads(prev_digest["item_ids"]))
            except Exception:
                pass
        if prev_ids:
            fresh = [i for i in pool if i.id not in prev_ids]
            seen  = [i for i in pool if i.id in prev_ids]
            pool  = fresh + seen
            logger.info("run_id=%s pool freshness: %d new, %d from prev digest (deprioritised)",
                        run_id, len(fresh), len(seen))

        logger.info("run_id=%s pool size: %d current + %d historical = %d",
                    run_id, len(ranked), len(pool) - len(ranked), len(pool))

        # --- Cluster ---
        t0 = time.monotonic()
        clusters = cluster(pool, bundle, repo, run_id)
        results.append(StageResult("cluster", len(pool), len(clusters), time.monotonic() - t0))
        repo.patch_pipeline_run(run_id, current_stage="compose")

        # --- Compose ---
        t0 = time.monotonic()
        digest: Digest = compose(pool, clusters, bundle, run_id)
        # Only replace an existing good digest if the new one meets the minimum.
        # This prevents a thin run from overwriting a richer previous digest.
        prev = repo.get_latest_digest(bundle.config.feed_id)
        if digest.item_count >= _DIGEST_MIN_ITEMS or prev is None:
            repo.insert_digest(digest)
        else:
            logger.warning(
                "run_id=%s digest skipped — only %d items (min %d); keeping previous digest",
                run_id, digest.item_count, _DIGEST_MIN_ITEMS,
            )
        results.append(StageResult("compose", len(ranked), digest.item_count, time.monotonic() - t0))

        finished_at = datetime.now(timezone.utc).isoformat()
        repo.update_pipeline_run(
            run_id,
            status="complete",
            finished_at=finished_at,
            items_fetched=len(raw_items),
            items_after_dedup=len(non_dupes),
            items_in_digest=digest.item_count,
            total_usd=total_usd,
        )
        logger.info("run_id=%s pipeline complete digest_items=%d", run_id, digest.item_count)

    except Exception as exc:
        finished_at = datetime.now(timezone.utc).isoformat()
        repo.update_pipeline_run(
            run_id,
            status="failed",
            finished_at=finished_at,
            error_message=str(exc),
        )
        logger.exception("run_id=%s pipeline failed: %s", run_id, exc)
        raise

    return results
