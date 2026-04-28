from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone

from niche.core.models.schema import create_schema
from niche.core.models.types import Digest, Item


class Repository:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    def create_schema(self) -> None:
        create_schema(self._conn)

    def close(self) -> None:
        self._conn.close()

    # --- pipeline runs ---

    def insert_pipeline_run(self, run_id: str, feed_id: str, started_at: str) -> None:
        self._conn.execute(
            "INSERT INTO pipeline_runs (id, feed_id, started_at, status) VALUES (?, ?, ?, 'running')",
            (run_id, feed_id, started_at),
        )
        self._conn.commit()

    def update_pipeline_run(
        self,
        run_id: str,
        *,
        status: str,
        finished_at: str,
        items_fetched: int = 0,
        items_after_dedup: int = 0,
        items_in_digest: int = 0,
        total_usd: float = 0.0,
        error_message: str | None = None,
    ) -> None:
        self._conn.execute(
            """UPDATE pipeline_runs SET
               status=?, finished_at=?, items_fetched=?, items_after_dedup=?,
               items_in_digest=?, total_usd=?, error_message=?
               WHERE id=?""",
            (
                status, finished_at, items_fetched, items_after_dedup,
                items_in_digest, total_usd, error_message, run_id,
            ),
        )
        self._conn.commit()

    # --- sources ---

    def upsert_source(self, source_dict: dict) -> None:
        self._conn.execute(
            """INSERT INTO sources (id, feed_id, source_type, url, name,
               default_region, default_topic, source_weight, enabled, added_by)
               VALUES (:id, :feed_id, :source_type, :url, :name,
               :default_region, :default_topic, :source_weight, :enabled, :added_by)
               ON CONFLICT(id) DO UPDATE SET
               name=excluded.name, url=excluded.url, source_weight=excluded.source_weight,
               enabled=excluded.enabled""",
            source_dict,
        )
        self._conn.commit()

    # --- items ---

    def get_url_hashes(self, feed_id: str, days: int = 7) -> set[str]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
        rows = self._conn.execute(
            "SELECT url_hash FROM items WHERE feed_id=? AND fetched_at >= ?",
            (feed_id, cutoff),
        ).fetchall()
        return {r["url_hash"] for r in rows}

    def get_title_hashes(self, feed_id: str, days: int = 7) -> set[str]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
        rows = self._conn.execute(
            "SELECT title_hash FROM items WHERE feed_id=? AND fetched_at >= ? AND title_hash IS NOT NULL",
            (feed_id, cutoff),
        ).fetchall()
        return {r["title_hash"] for r in rows}

    def get_recent_titles(self, feed_id: str, days: int = 7) -> list[str]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()
        rows = self._conn.execute(
            "SELECT title FROM items WHERE feed_id=? AND fetched_at >= ? AND title IS NOT NULL",
            (feed_id, cutoff),
        ).fetchall()
        return [r["title"] for r in rows]

    def update_source_health(
        self,
        source_id: str,
        feed_id: str,
        *,
        success: bool,
        error_message: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        if success:
            self._conn.execute(
                """INSERT INTO source_health (source_id, feed_id, last_ok_at, consecutive_failures, is_flagged)
                   VALUES (?, ?, ?, 0, 0)
                   ON CONFLICT(source_id) DO UPDATE SET
                   last_ok_at=excluded.last_ok_at,
                   consecutive_failures=0,
                   is_flagged=0""",
                (source_id, feed_id, now),
            )
        else:
            self._conn.execute(
                """INSERT INTO source_health
                   (source_id, feed_id, last_error_at, last_error_message, consecutive_failures, is_flagged)
                   VALUES (?, ?, ?, ?, 1, 0)
                   ON CONFLICT(source_id) DO UPDATE SET
                   last_error_at=excluded.last_error_at,
                   last_error_message=excluded.last_error_message,
                   consecutive_failures=consecutive_failures+1,
                   is_flagged=CASE WHEN consecutive_failures+1 >= 3 THEN 1 ELSE 0 END""",
                (source_id, feed_id, now, error_message),
            )
        self._conn.commit()

    def insert_items(self, items: list[Item]) -> None:
        rows = [self._serialize_item(item) for item in items]
        self._conn.executemany(
            """INSERT OR IGNORE INTO items
               (id, feed_id, url, url_hash, title_hash, title, title_translated, body_raw, body_translated,
                summary, why_it_matters, source_id, source_name, source_language,
                topic_tag, item_type, region_tag, company_tags,
                translation_failed, translation_provider, relevance_score,
                published_at, fetched_at, run_id, word_count, read_time_min,
                is_duplicate, duplicate_of)
               VALUES
               (:id, :feed_id, :url, :url_hash, :title_hash, :title, :title_translated, :body_raw, :body_translated,
                :summary, :why_it_matters, :source_id, :source_name, :source_language,
                :topic_tag, :item_type, :region_tag, :company_tags,
                :translation_failed, :translation_provider, :relevance_score,
                :published_at, :fetched_at, :run_id, :word_count, :read_time_min,
                :is_duplicate, :duplicate_of)""",
            rows,
        )
        self._conn.commit()

    def update_items(self, items: list[Item]) -> None:
        rows = [self._serialize_item(item) for item in items]
        self._conn.executemany(
            """UPDATE items SET
               topic_tag=:topic_tag, item_type=:item_type, region_tag=:region_tag,
               company_tags=:company_tags, translation_failed=:translation_failed,
               translation_provider=:translation_provider,
               title_translated=:title_translated, body_translated=:body_translated,
               summary=:summary, why_it_matters=:why_it_matters,
               word_count=:word_count, read_time_min=:read_time_min,
               relevance_score=:relevance_score
               WHERE id=:id""",
            rows,
        )
        self._conn.commit()

    # --- digests ---

    def insert_digest(self, digest: Digest) -> None:
        self._conn.execute(
            """INSERT INTO digests
               (id, feed_id, user_id, run_id, date, item_ids, cluster_map,
                total_read_time_min, item_count, created_at, email_sent_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                digest.id, digest.feed_id, digest.user_id, digest.run_id,
                digest.date, json.dumps(digest.item_ids),
                json.dumps(digest.cluster_map),
                digest.total_read_time_min, digest.item_count,
                digest.created_at, digest.email_sent_at,
            ),
        )
        self._conn.commit()

    # --- users ---

    def get_user_by_email(self, email: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM users WHERE email=? AND deleted_at IS NULL", (email,)
        ).fetchone()

    def upsert_user_admin(self, email: str, feed_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO users (id, feed_id, email, is_admin, is_approved, created_at)
               VALUES (lower(hex(randomblob(16))), ?, ?, 1, 1, ?)
               ON CONFLICT(email) DO UPDATE SET is_admin=1, is_approved=1""",
            (feed_id, email, now),
        )
        self._conn.commit()

    # --- helpers ---

    def _serialize_item(self, item: Item) -> dict:
        return {
            "id": item.id,
            "feed_id": item.feed_id,
            "url": item.url,
            "url_hash": item.url_hash,
            "title_hash": item.title_hash,
            "title": item.title,
            "title_translated": item.title_translated,
            "body_raw": item.body_raw,
            "body_translated": item.body_translated,
            "summary": item.summary,
            "why_it_matters": item.why_it_matters,
            "source_id": item.source_id,
            "source_name": item.source_name,
            "source_language": item.source_language,
            "topic_tag": item.topic_tag,
            "item_type": item.item_type,
            "region_tag": item.region_tag,
            "company_tags": json.dumps(item.company_tags),
            "translation_failed": int(item.translation_failed),
            "translation_provider": item.translation_provider,
            "relevance_score": item.relevance_score,
            "published_at": item.published_at.isoformat() if item.published_at else None,
            "fetched_at": item.fetched_at.isoformat(),
            "run_id": item.run_id,
            "word_count": item.word_count,
            "read_time_min": item.read_time_min,
            "is_duplicate": int(item.is_duplicate),
            "duplicate_of": item.duplicate_of,
        }
