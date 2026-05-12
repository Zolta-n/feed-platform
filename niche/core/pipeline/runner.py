"""
Pipeline runner — orchestrates all stages, threads run_id (EP3).

Usage:
    runner = PipelineRunner(bundle, repo, db_path)
    run_id = runner.run()
"""
from __future__ import annotations

import datetime
import logging
import time
import uuid
from typing import Optional

from ..models.repository import Repository
from ..models.types import FeedBundle, PipelineRun
from ..sources.factory import build_sources
from ..sources.retry import fetch_with_retry
from .classify import classify
from .cluster import cluster
from .compose import compose
from .dedup import dedup
from .rank import rank
from .summarize import summarize
from .translate import translate

logger = logging.getLogger(__name__)


class PipelineRunner:
    """Runs the full pipeline: Fetch→Dedup→Classify→Translate→Summarize→Rank→Cluster→Compose."""

    def __init__(
        self,
        bundle: FeedBundle,
        repo: Repository,
        *,
        classifier=None,
        summarizer=None,
        translator=None,
        labeler=None,
        run_id: Optional[str] = None,
    ) -> None:
        self.bundle = bundle
        self.repo = repo
        self.classifier = classifier
        self.summarizer = summarizer
        self.translator = translator
        self.labeler = labeler
        self.run_id = run_id or str(uuid.uuid4())

    def run(self) -> str:
        """Execute the full pipeline. Returns run_id."""
        run = PipelineRun(
            id=self.run_id,
            feed_id=self.bundle.config.feed_id,
            started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        )

        with self.repo.connect() as conn:
            self.repo.insert_pipeline_run(conn, run)

        try:
            self._run_pipeline(run)
        except Exception as exc:
            logger.exception("Pipeline run %s failed: %s", self.run_id, exc)
            run.status = "failed"
            run.error_message = str(exc)
            run.finished_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            with self.repo.connect() as conn:
                self.repo.update_pipeline_run(conn, run)

        return self.run_id

    def _run_pipeline(self, run: PipelineRun) -> None:
        feed_id = self.bundle.config.feed_id

        # ---------------------------------------------------------------- Fetch
        self._update_stage(run, "fetch")
        sources = build_sources(self.bundle.sources, self.bundle)
        raw_items = []
        for source in sources:
            items_from_source = fetch_with_retry(
                source.source_id, source.fetch
            )
            raw_items.extend(items_from_source)
        run.items_fetched = len(raw_items)
        logger.info("[%s] Fetch: %d raw items", self.run_id, len(raw_items))

        if not raw_items:
            run.status = "complete"
            run.items_in_digest = 0
            run.finished_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
            with self.repo.connect() as conn:
                self.repo.update_pipeline_run(conn, run)
            return

        # ---------------------------------------------------------------- Dedup
        self._update_stage(run, "dedup")
        with self.repo.connect() as conn:
            existing_url_hashes = self.repo.get_url_hashes(conn, feed_id)
            existing_title_hashes = self.repo.get_title_hashes(conn, feed_id)
            recent_titles = self.repo.get_recent_titles(conn, feed_id)

        items = dedup(
            raw_items, feed_id,
            existing_url_hashes, existing_title_hashes, recent_titles,
            run_id=self.run_id,
        )
        unique = [i for i in items if not i.is_duplicate]
        run.items_after_dedup = len(unique)

        with self.repo.connect() as conn:
            for item in items:
                self.repo.insert_item(conn, item)

        logger.info("[%s] Dedup: %d unique", self.run_id, len(unique))

        # -------------------------------------------------------------- Classify
        self._update_stage(run, "classify")
        items = classify(items, self.bundle, self.classifier)
        with self.repo.connect() as conn:
            for item in items:
                if not item.is_duplicate:
                    self.repo.update_item(conn, item)

        # -------------------------------------------------------------- Translate
        self._update_stage(run, "translate")
        items = translate(items, self.bundle, translator=self.translator)
        with self.repo.connect() as conn:
            for item in items:
                if not item.is_duplicate:
                    self.repo.update_item(conn, item)

        # -------------------------------------------------------------- Summarize
        self._update_stage(run, "summarize")
        items = summarize(items, self.bundle, self.summarizer)
        with self.repo.connect() as conn:
            for item in items:
                if not item.is_duplicate:
                    self.repo.update_item(conn, item)

        # ----------------------------------------------------------------- Rank
        self._update_stage(run, "rank")
        ranked = rank(items, self.bundle)
        with self.repo.connect() as conn:
            for item in ranked:
                self.repo.update_item(conn, item)

        # --------------------------------------------------------------- Cluster
        self._update_stage(run, "cluster")
        ranked, clusters = cluster(ranked, self.bundle, self.labeler)

        # -------------------------------------------------------------- Compose
        self._update_stage(run, "compose")
        digest = compose(
            ranked, clusters, self.bundle,
            run_id=self.run_id,
            date=datetime.date.today().isoformat(),
        )
        with self.repo.connect() as conn:
            self.repo.insert_digest(conn, digest)

        run.items_in_digest = digest.item_count
        run.status = "complete"
        run.finished_at = datetime.datetime.now(datetime.timezone.utc).isoformat()
        run.current_stage = None
        with self.repo.connect() as conn:
            self.repo.update_pipeline_run(conn, run)

        logger.info(
            "[%s] Pipeline complete: %d items in digest",
            self.run_id, digest.item_count,
        )

    def _update_stage(self, run: PipelineRun, stage: str) -> None:
        run.current_stage = stage
        with self.repo.connect() as conn:
            self.repo.update_pipeline_run(conn, run)
        logger.info("[%s] Stage: %s", self.run_id, stage)
