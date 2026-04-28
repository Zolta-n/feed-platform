from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from niche.core.models.types import Digest, FeedBundle, Item
from niche.core.models.repository import Repository
from niche.core.pipeline.classify import classify
from niche.core.pipeline.cluster import cluster
from niche.core.pipeline.compose import compose
from niche.core.pipeline.dedup import dedup
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

        # --- Classify ---
        t0 = time.monotonic()
        classified = classify(non_dupes, bundle, repo, run_id)
        repo.update_items(classified)
        logger.info("run_id=%s classify out=%d", run_id, len(classified))
        results.append(StageResult("classify", len(non_dupes), len(classified), time.monotonic() - t0))

        # --- Translate ---
        t0 = time.monotonic()
        translated = translate(classified, bundle, repo, run_id)
        repo.update_items(translated)
        results.append(StageResult("translate", len(classified), len(translated), time.monotonic() - t0))

        # --- Summarize ---
        t0 = time.monotonic()
        summarized = summarize(translated, bundle, repo, run_id)
        repo.update_items(summarized)
        results.append(StageResult("summarize", len(translated), len(summarized), time.monotonic() - t0))

        # --- Rank ---
        t0 = time.monotonic()
        ranked = rank(summarized, bundle, preferences={}, repo=repo)
        repo.update_items(ranked)
        results.append(StageResult("rank", len(summarized), len(ranked), time.monotonic() - t0))

        # --- Cluster ---
        t0 = time.monotonic()
        clusters = cluster(ranked, bundle, repo, run_id)
        results.append(StageResult("cluster", len(ranked), len(clusters), time.monotonic() - t0))

        # --- Compose ---
        t0 = time.monotonic()
        digest: Digest = compose(ranked, clusters, bundle, run_id)
        repo.insert_digest(digest)
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
