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
                is_duplicate, duplicate_of, image_url)
               VALUES
               (:id, :feed_id, :url, :url_hash, :title_hash, :title, :title_translated, :body_raw, :body_translated,
                :summary, :why_it_matters, :source_id, :source_name, :source_language,
                :topic_tag, :item_type, :region_tag, :company_tags,
                :translation_failed, :translation_provider, :relevance_score,
                :published_at, :fetched_at, :run_id, :word_count, :read_time_min,
                :is_duplicate, :duplicate_of, :image_url)""",
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

    # --- llm cost ---

    def insert_llm_cost(
        self,
        *,
        feed_id: str,
        run_id: str | None,
        agent: str,
        model: str,
        prompt_name: str | None,
        prompt_version: int | None,
        input_tokens: int,
        output_tokens: int,
        cache_read_tokens: int,
        cache_write_tokens: int,
        usd: float,
    ) -> None:
        import uuid
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO llm_cost_log
               (id, feed_id, run_id, agent, model, prompt_name, prompt_version,
                input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                usd, called_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                uuid.uuid4().hex, feed_id, run_id, agent, model,
                prompt_name, prompt_version,
                input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                usd, now,
            ),
        )
        self._conn.commit()

    def get_daily_cost_usd(self, feed_id: str) -> float:
        today = datetime.now(timezone.utc).date().isoformat()
        row = self._conn.execute(
            "SELECT COALESCE(SUM(usd), 0.0) FROM llm_cost_log WHERE feed_id=? AND called_at >= ?",
            (feed_id, today),
        ).fetchone()
        return row[0] if row else 0.0

    # --- users ---

    def get_user_by_email(self, email: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM users WHERE email=? AND deleted_at IS NULL", (email,)
        ).fetchone()

    def get_user_by_id(self, user_id: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM users WHERE id=? AND deleted_at IS NULL", (user_id,)
        ).fetchone()

    def create_user(self, email: str, feed_id: str) -> str:
        import uuid
        user_id = uuid.uuid4().hex
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO users (id, feed_id, email, is_admin, is_approved, created_at)
               VALUES (?, ?, ?, 0, 0, ?)""",
            (user_id, feed_id, email, now),
        )
        self._conn.commit()
        return user_id

    def approve_user(self, user_id: str) -> None:
        self._conn.execute(
            "UPDATE users SET is_approved=1 WHERE id=?", (user_id,)
        )
        self._conn.commit()

    def get_admin_users(self, feed_id: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM users WHERE feed_id=? AND is_admin=1 AND deleted_at IS NULL",
            (feed_id,),
        ).fetchall()

    def get_all_users(self, feed_id: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM users WHERE feed_id=? AND deleted_at IS NULL ORDER BY created_at DESC",
            (feed_id,),
        ).fetchall()

    def update_last_seen(self, user_id: str) -> None:
        self._conn.execute(
            "UPDATE users SET last_seen_at=? WHERE id=?",
            (datetime.now(timezone.utc).isoformat(), user_id),
        )
        self._conn.commit()

    def upsert_user_admin(self, email: str, feed_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO users (id, feed_id, email, is_admin, is_approved, created_at)
               VALUES (lower(hex(randomblob(16))), ?, ?, 1, 1, ?)
               ON CONFLICT(email) DO UPDATE SET is_admin=1, is_approved=1""",
            (feed_id, email, now),
        )
        self._conn.commit()

    def delete_user(self, user_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute("UPDATE users SET deleted_at=? WHERE id=?", (now, user_id))
        self._conn.execute("DELETE FROM preferences WHERE user_id=?", (user_id,))
        self._conn.execute("DELETE FROM read_log WHERE user_id=?", (user_id,))
        self._conn.execute("UPDATE feedback SET user_id=NULL WHERE user_id=?", (user_id,))
        self._conn.execute("DELETE FROM magic_link_tokens WHERE email=(SELECT email FROM users WHERE id=?)", (user_id,))
        self._conn.commit()

    # --- saved items ---

    def toggle_saved(self, user_id: str, item_id: str, feed_id: str) -> bool:
        """Toggle saved state. Returns True if now saved, False if removed."""
        existing = self._conn.execute(
            "SELECT id FROM saved_items WHERE user_id=? AND item_id=?", (user_id, item_id)
        ).fetchone()
        if existing:
            self._conn.execute("DELETE FROM saved_items WHERE user_id=? AND item_id=?", (user_id, item_id))
            self._conn.commit()
            return False
        import uuid
        self._conn.execute(
            "INSERT INTO saved_items (id, feed_id, user_id, item_id, saved_at) VALUES (?,?,?,?,?)",
            (uuid.uuid4().hex, feed_id, user_id, item_id, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()
        return True

    def get_saved_item_ids(self, user_id: str, feed_id: str) -> set[str]:
        rows = self._conn.execute(
            "SELECT item_id FROM saved_items WHERE user_id=? AND feed_id=?", (user_id, feed_id)
        ).fetchall()
        return {r["item_id"] for r in rows}

    def get_saved_items(self, user_id: str, feed_id: str) -> list:
        return self._conn.execute(
            """SELECT i.* FROM items i
               JOIN saved_items s ON s.item_id=i.id
               WHERE s.user_id=? AND s.feed_id=?
               ORDER BY s.saved_at DESC""",
            (user_id, feed_id),
        ).fetchall()

    # --- share tokens ---

    def create_share_token(self, item_id: str, feed_id: str) -> str:
        import secrets
        from datetime import timedelta
        token = secrets.token_urlsafe(24)
        expires_at = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT OR REPLACE INTO share_tokens (token, item_id, feed_id, expires_at, created_at) VALUES (?,?,?,?,?)",
            (token, item_id, feed_id, expires_at, now),
        )
        self._conn.commit()
        return token

    def get_share_token(self, token: str):
        return self._conn.execute(
            "SELECT * FROM share_tokens WHERE token=?", (token,)
        ).fetchone()

    def get_item_by_id(self, item_id: str):
        return self._conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()

    def get_breaking_items(self, feed_id: str, limit: int = 8) -> list:
        return self._conn.execute(
            """SELECT * FROM items
               WHERE feed_id=? AND item_type='breaking' AND is_duplicate=0
               ORDER BY published_at DESC, fetched_at DESC
               LIMIT ?""",
            (feed_id, limit),
        ).fetchall()

    def prune_read_log(self, days: int = 180) -> int:
        """Delete read_log entries older than `days`. Returns number of rows deleted."""
        from datetime import timedelta
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        cur = self._conn.execute("DELETE FROM read_log WHERE read_at < ?", (cutoff,))
        self._conn.commit()
        return cur.rowcount

    # --- magic link tokens ---

    def create_magic_link_token(self, email: str, expires_at: str) -> str:
        import secrets
        token = secrets.token_hex(32)
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO magic_link_tokens (token, email, expires_at, used, created_at)
               VALUES (?, ?, ?, 0, ?)""",
            (token, email, expires_at, now),
        )
        self._conn.commit()
        return token

    def get_magic_link_token(self, token: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM magic_link_tokens WHERE token=?", (token,)
        ).fetchone()

    def mark_token_used(self, token: str) -> None:
        self._conn.execute(
            "UPDATE magic_link_tokens SET used=1 WHERE token=?", (token,)
        )
        self._conn.commit()

    # --- digests ---

    def get_latest_digest(self, feed_id: str) -> sqlite3.Row | None:
        return self._conn.execute(
            """SELECT * FROM digests WHERE feed_id=? AND user_id IS NULL
               ORDER BY date DESC LIMIT 1""",
            (feed_id,),
        ).fetchone()

    def get_digest_by_date(self, feed_id: str, date: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM digests WHERE feed_id=? AND date=? AND user_id IS NULL",
            (feed_id, date),
        ).fetchone()

    def get_items_by_ids(self, ids: list[str]) -> list[sqlite3.Row]:
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        rows = self._conn.execute(
            f"SELECT * FROM items WHERE id IN ({placeholders})", ids
        ).fetchall()
        id_order = {iid: pos for pos, iid in enumerate(ids)}
        return sorted(rows, key=lambda r: id_order.get(r["id"], len(ids)))

    def get_item(self, item_id: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM items WHERE id=?", (item_id,)
        ).fetchone()

    # --- preferences ---

    def get_user_preferences(self, user_id: str) -> sqlite3.Row | None:
        return self._conn.execute(
            "SELECT * FROM preferences WHERE user_id=?", (user_id,)
        ).fetchone()

    def save_user_preferences(self, user_id: str, feed_id: str, prefs: dict) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO preferences (id, user_id, feed_id, region_weights, topic_weights,
               company_boosts, keyword_boosts, keyword_blocks, theme_color, updated_at)
               VALUES (lower(hex(randomblob(16))), ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
               region_weights=excluded.region_weights,
               topic_weights=excluded.topic_weights,
               company_boosts=excluded.company_boosts,
               keyword_boosts=excluded.keyword_boosts,
               keyword_blocks=excluded.keyword_blocks,
               theme_color=excluded.theme_color,
               updated_at=excluded.updated_at""",
            (
                user_id, feed_id,
                json.dumps(prefs.get("region_weights", {})),
                json.dumps(prefs.get("topic_weights", {})),
                json.dumps(prefs.get("company_boosts", {})),
                json.dumps(prefs.get("keyword_boosts", {})),
                json.dumps(prefs.get("keyword_blocks", [])),
                prefs.get("theme_color", "red"),
                now,
            ),
        )
        self._conn.commit()

    # --- feedback ---

    def insert_feedback(self, feed_id: str, user_id: str, item_id: str, signal: str) -> None:
        import uuid
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT INTO feedback (id, feed_id, user_id, item_id, signal, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (uuid.uuid4().hex, feed_id, user_id, item_id, signal, now),
        )
        self._conn.commit()

    def mark_item_read(self, feed_id: str, user_id: str, item_id: str, source: str = "web") -> None:
        import uuid
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """INSERT OR IGNORE INTO read_log (id, feed_id, user_id, item_id, source, read_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (uuid.uuid4().hex, feed_id, user_id, item_id, source, now),
        )
        self._conn.commit()

    def get_read_item_ids(self, user_id: str, item_ids: list[str]) -> set[str]:
        if not item_ids:
            return set()
        placeholders = ",".join("?" * len(item_ids))
        rows = self._conn.execute(
            f"SELECT item_id FROM read_log WHERE user_id=? AND item_id IN ({placeholders})",
            [user_id] + item_ids,
        ).fetchall()
        return {r["item_id"] for r in rows}

    # --- archive ---

    def get_archive_items(
        self,
        feed_id: str,
        *,
        keyword: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        limit: int = 50,
    ) -> list[sqlite3.Row]:
        query = "SELECT * FROM items WHERE feed_id=? AND is_duplicate=0 AND summary IS NOT NULL"
        params: list = [feed_id]
        if keyword:
            query += " AND (title LIKE ? OR summary LIKE ?)"
            like = f"%{keyword}%"
            params.extend([like, like])
        if date_from:
            query += " AND fetched_at >= ?"
            params.append(date_from)
        if date_to:
            query += " AND fetched_at <= ?"
            params.append(date_to + "T23:59:59")
        query += " ORDER BY fetched_at DESC LIMIT ?"
        params.append(limit)
        return self._conn.execute(query, params).fetchall()

    # --- admin ---

    def get_pipeline_runs(self, feed_id: str, limit: int = 7) -> list[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM pipeline_runs WHERE feed_id=? ORDER BY started_at DESC LIMIT ?",
            (feed_id, limit),
        ).fetchall()

    def get_all_source_health(self, feed_id: str) -> list[sqlite3.Row]:
        return self._conn.execute(
            """SELECT s.id, s.name, s.source_type, s.url, s.enabled,
                      sh.last_ok_at, sh.last_error_at, sh.last_error_message,
                      sh.consecutive_failures, sh.is_flagged
               FROM sources s
               LEFT JOIN source_health sh ON sh.source_id = s.id
               WHERE s.feed_id=?
               ORDER BY s.name""",
            (feed_id,),
        ).fetchall()

    def get_llm_costs_summary(self, feed_id: str, days: int = 30) -> list[sqlite3.Row]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        return self._conn.execute(
            """SELECT agent, model, prompt_name,
                      SUM(input_tokens) as input_tokens,
                      SUM(output_tokens) as output_tokens,
                      SUM(cache_read_tokens) as cache_read_tokens,
                      SUM(usd) as usd,
                      COUNT(*) as call_count
               FROM llm_cost_log
               WHERE feed_id=? AND called_at >= ?
               GROUP BY agent, model, prompt_name
               ORDER BY usd DESC""",
            (feed_id, cutoff),
        ).fetchall()

    # --- GDPR ---

    def export_user_data(self, user_id: str) -> dict:
        user = self.get_user_by_id(user_id)
        prefs = self.get_user_preferences(user_id)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=180)).isoformat()
        reads = self._conn.execute(
            "SELECT item_id, source, read_at FROM read_log WHERE user_id=? AND read_at>=? AND pruned=0",
            (user_id, cutoff),
        ).fetchall()
        feedback = self._conn.execute(
            "SELECT item_id, signal, created_at FROM feedback WHERE user_id=?",
            (user_id,),
        ).fetchall()
        return {
            "user": dict(user) if user else {},
            "preferences": dict(prefs) if prefs else {},
            "read_log": [dict(r) for r in reads],
            "feedback": [dict(f) for f in feedback],
        }

    def prune_old_read_log(self) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=180)).isoformat()
        cur = self._conn.execute(
            "UPDATE read_log SET pruned=1 WHERE read_at < ? AND pruned=0", (cutoff,)
        )
        self._conn.commit()
        return cur.rowcount

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
            "image_url": item.image_url,
        }
