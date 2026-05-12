"""
Repository — SQLite storage interface (EP6).

All database access goes through this class. Swapping to PostgreSQL
is a single-file change: implement the same interface on top of psycopg2.

Usage:
    repo = Repository(db_path)
    with repo.connect() as conn:
        items = repo.get_items(conn, feed_id=..., limit=20)

The Repository does NOT hold a long-lived connection; callers manage the
connection lifetime (Flask uses g.db, the pipeline uses a with-block).
"""
from __future__ import annotations

import json
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Generator, Optional

from .types import (
    Digest, FeedBundle, Item, LlmCostEntry, Preferences, PipelineRun,
    SourceConfig, SourceHealth, User, WatchlistEntry,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_item(row: sqlite3.Row) -> Item:
    d = dict(row)
    return Item(
        id=d["id"],
        feed_id=d["feed_id"],
        url=d["url"],
        url_hash=d["url_hash"],
        title_hash=d.get("title_hash"),
        title=d.get("title"),
        title_translated=d.get("title_translated"),
        body_raw=d.get("body_raw"),
        body_translated=d.get("body_translated"),
        summary=d.get("summary"),
        why_it_matters=d.get("why_it_matters"),
        source_id=d.get("source_id"),
        source_name=d.get("source_name"),
        source_language=d.get("source_language", "en"),
        topic_tag=d.get("topic_tag"),
        item_type=d.get("item_type"),
        region_tag=d.get("region_tag"),
        company_tags=Item.company_tags_from_json(d.get("company_tags", "[]")),
        translation_failed=bool(d.get("translation_failed", 0)),
        translation_provider=d.get("translation_provider"),
        relevance_score=d.get("relevance_score", 0.0),
        published_at=d.get("published_at"),
        fetched_at=d.get("fetched_at", ""),
        run_id=d.get("run_id"),
        word_count=d.get("word_count", 0),
        read_time_min=d.get("read_time_min", 0.0),
        is_duplicate=bool(d.get("is_duplicate", 0)),
        duplicate_of=d.get("duplicate_of"),
        image_url=d.get("image_url"),
    )


def _row_to_user(row: sqlite3.Row) -> User:
    d = dict(row)
    return User(
        id=d["id"],
        feed_id=d["feed_id"],
        email=d["email"],
        is_admin=bool(d.get("is_admin", 0)),
        is_approved=bool(d.get("is_approved", 0)),
        ui_language=d.get("ui_language", "en"),
        created_at=d.get("created_at", ""),
        last_seen_at=d.get("last_seen_at"),
        email_enabled=bool(d.get("email_enabled", 1)),
        email_send_time=d.get("email_send_time", "06:30"),
        email_item_count=d.get("email_item_count", 15),
        deleted_at=d.get("deleted_at"),
    )


def _row_to_preferences(row: sqlite3.Row) -> Preferences:
    d = dict(row)
    return Preferences(
        id=d["id"],
        user_id=d["user_id"],
        feed_id=d["feed_id"],
        region_weights=json.loads(d.get("region_weights", "{}")),
        topic_weights=json.loads(d.get("topic_weights", "{}")),
        company_boosts=json.loads(d.get("company_boosts", "{}")),
        keyword_boosts=json.loads(d.get("keyword_boosts", "[]")),
        keyword_blocks=json.loads(d.get("keyword_blocks", "[]")),
        updated_at=d.get("updated_at", ""),
        theme_color=d.get("theme_color", "red"),
    )


def _row_to_digest(row: sqlite3.Row) -> Digest:
    d = dict(row)
    return Digest(
        id=d["id"],
        feed_id=d["feed_id"],
        date=d["date"],
        item_ids=json.loads(d.get("item_ids", "[]")),
        cluster_map=json.loads(d.get("cluster_map", "[]")),
        total_read_time_min=d.get("total_read_time_min", 0.0),
        item_count=d.get("item_count", 0),
        created_at=d.get("created_at", ""),
        user_id=d.get("user_id"),
        run_id=d.get("run_id"),
        email_sent_at=d.get("email_sent_at"),
    )


class Repository:
    """SQLite storage backend.  Every public method accepts a connection
    as the first argument so callers control the transaction boundary."""

    def __init__(self, db_path: str) -> None:
        self.db_path = db_path

    @contextmanager
    def connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA journal_mode=WAL")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------------
    # Items
    # ------------------------------------------------------------------

    def insert_item(self, conn: sqlite3.Connection, item: Item) -> None:
        conn.execute(
            """INSERT OR IGNORE INTO items (
                id, feed_id, url, url_hash, title_hash, title, title_translated,
                body_raw, body_translated, summary, why_it_matters,
                source_id, source_name, source_language,
                topic_tag, item_type, region_tag, company_tags,
                translation_failed, translation_provider,
                relevance_score, published_at, fetched_at, run_id,
                word_count, read_time_min, is_duplicate, duplicate_of, image_url
            ) VALUES (
                :id, :feed_id, :url, :url_hash, :title_hash, :title, :title_translated,
                :body_raw, :body_translated, :summary, :why_it_matters,
                :source_id, :source_name, :source_language,
                :topic_tag, :item_type, :region_tag, :company_tags,
                :translation_failed, :translation_provider,
                :relevance_score, :published_at, :fetched_at, :run_id,
                :word_count, :read_time_min, :is_duplicate, :duplicate_of, :image_url
            )""",
            {
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
                "company_tags": item.company_tags_json(),
                "translation_failed": int(item.translation_failed),
                "translation_provider": item.translation_provider,
                "relevance_score": item.relevance_score,
                "published_at": item.published_at,
                "fetched_at": item.fetched_at,
                "run_id": item.run_id,
                "word_count": item.word_count,
                "read_time_min": item.read_time_min,
                "is_duplicate": int(item.is_duplicate),
                "duplicate_of": item.duplicate_of,
                "image_url": item.image_url,
            },
        )

    def update_item(self, conn: sqlite3.Connection, item: Item) -> None:
        conn.execute(
            """UPDATE items SET
                title_translated=:title_translated,
                body_raw=:body_raw, body_translated=:body_translated,
                summary=:summary, why_it_matters=:why_it_matters,
                topic_tag=:topic_tag, item_type=:item_type, region_tag=:region_tag,
                company_tags=:company_tags,
                translation_failed=:translation_failed,
                translation_provider=:translation_provider,
                relevance_score=:relevance_score,
                word_count=:word_count, read_time_min=:read_time_min,
                is_duplicate=:is_duplicate, duplicate_of=:duplicate_of,
                image_url=:image_url
            WHERE id=:id""",
            {
                "id": item.id,
                "title_translated": item.title_translated,
                "body_raw": item.body_raw,
                "body_translated": item.body_translated,
                "summary": item.summary,
                "why_it_matters": item.why_it_matters,
                "topic_tag": item.topic_tag,
                "item_type": item.item_type,
                "region_tag": item.region_tag,
                "company_tags": item.company_tags_json(),
                "translation_failed": int(item.translation_failed),
                "translation_provider": item.translation_provider,
                "relevance_score": item.relevance_score,
                "word_count": item.word_count,
                "read_time_min": item.read_time_min,
                "is_duplicate": int(item.is_duplicate),
                "duplicate_of": item.duplicate_of,
                "image_url": item.image_url,
            },
        )

    def get_item(self, conn: sqlite3.Connection, item_id: str) -> Optional[Item]:
        row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
        return _row_to_item(row) if row else None

    def get_items(
        self,
        conn: sqlite3.Connection,
        feed_id: str,
        *,
        limit: int = 50,
        offset: int = 0,
        topic_tag: Optional[str] = None,
        run_id: Optional[str] = None,
        exclude_duplicates: bool = True,
        order_by: str = "relevance_score DESC",
    ) -> list[Item]:
        where = ["feed_id=?"]
        params: list[Any] = [feed_id]
        if topic_tag:
            where.append("topic_tag=?")
            params.append(topic_tag)
        if run_id:
            where.append("run_id=?")
            params.append(run_id)
        if exclude_duplicates:
            where.append("is_duplicate=0")
        sql = (
            f"SELECT * FROM items WHERE {' AND '.join(where)}"
            f" ORDER BY {order_by} LIMIT ? OFFSET ?"
        )
        params += [limit, offset]
        rows = conn.execute(sql, params).fetchall()
        return [_row_to_item(r) for r in rows]

    def get_items_by_ids(
        self, conn: sqlite3.Connection, item_ids: list[str]
    ) -> list[Item]:
        if not item_ids:
            return []
        placeholders = ",".join("?" * len(item_ids))
        rows = conn.execute(
            f"SELECT * FROM items WHERE id IN ({placeholders})", item_ids
        ).fetchall()
        # Preserve requested order
        by_id = {r["id"]: _row_to_item(r) for r in rows}
        return [by_id[i] for i in item_ids if i in by_id]

    def get_url_hashes(
        self, conn: sqlite3.Connection, feed_id: str, days: int = 7
    ) -> set[str]:
        rows = conn.execute(
            "SELECT url_hash FROM items WHERE feed_id=? AND fetched_at >= datetime('now', ?)",
            (feed_id, f"-{days} days"),
        ).fetchall()
        return {r["url_hash"] for r in rows}

    def get_title_hashes(
        self, conn: sqlite3.Connection, feed_id: str, days: int = 7
    ) -> set[str]:
        rows = conn.execute(
            "SELECT title_hash FROM items WHERE feed_id=? AND title_hash IS NOT NULL"
            " AND fetched_at >= datetime('now', ?)",
            (feed_id, f"-{days} days"),
        ).fetchall()
        return {r["title_hash"] for r in rows}

    def get_recent_titles(
        self, conn: sqlite3.Connection, feed_id: str, days: int = 7
    ) -> list[tuple[str, str]]:
        """Return (id, title) for recent non-duplicate items."""
        rows = conn.execute(
            "SELECT id, title FROM items WHERE feed_id=? AND is_duplicate=0"
            " AND title IS NOT NULL AND fetched_at >= datetime('now', ?)",
            (feed_id, f"-{days} days"),
        ).fetchall()
        return [(r["id"], r["title"]) for r in rows]

    def search_items(
        self,
        conn: sqlite3.Connection,
        feed_id: str,
        query: str,
        *,
        limit: int = 50,
        offset: int = 0,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
    ) -> list[Item]:
        where = ["feed_id=?", "is_duplicate=0"]
        params: list[Any] = [feed_id]
        if query:
            where.append("(title LIKE ? OR summary LIKE ?)")
            like = f"%{query}%"
            params += [like, like]
        if date_from:
            where.append("fetched_at >= ?")
            params.append(date_from)
        if date_to:
            where.append("fetched_at <= ?")
            params.append(date_to + "T23:59:59")
        sql = (
            f"SELECT * FROM items WHERE {' AND '.join(where)}"
            f" ORDER BY fetched_at DESC LIMIT ? OFFSET ?"
        )
        params += [limit, offset]
        rows = conn.execute(sql, params).fetchall()
        return [_row_to_item(r) for r in rows]

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------

    def get_user(self, conn: sqlite3.Connection, user_id: str) -> Optional[User]:
        row = conn.execute(
            "SELECT * FROM users WHERE id=? AND deleted_at IS NULL", (user_id,)
        ).fetchone()
        return _row_to_user(row) if row else None

    def get_user_by_email(
        self, conn: sqlite3.Connection, email: str
    ) -> Optional[User]:
        row = conn.execute(
            "SELECT * FROM users WHERE email=? AND deleted_at IS NULL", (email,)
        ).fetchone()
        return _row_to_user(row) if row else None

    def get_first_admin(self, conn: sqlite3.Connection) -> Optional[User]:
        row = conn.execute(
            "SELECT * FROM users WHERE is_approved=1 AND deleted_at IS NULL ORDER BY created_at LIMIT 1"
        ).fetchone()
        return _row_to_user(row) if row else None

    def insert_user(self, conn: sqlite3.Connection, user: User) -> None:
        conn.execute(
            """INSERT INTO users
               (id, feed_id, email, is_admin, is_approved, ui_language,
                created_at, last_seen_at, email_enabled, email_send_time,
                email_item_count, deleted_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                user.id, user.feed_id, user.email,
                int(user.is_admin), int(user.is_approved),
                user.ui_language, user.created_at, user.last_seen_at,
                int(user.email_enabled), user.email_send_time,
                user.email_item_count, user.deleted_at,
            ),
        )

    def update_user(self, conn: sqlite3.Connection, user: User) -> None:
        conn.execute(
            """UPDATE users SET
                is_admin=?, is_approved=?, ui_language=?, last_seen_at=?,
                email_enabled=?, email_send_time=?, email_item_count=?,
                deleted_at=?
               WHERE id=?""",
            (
                int(user.is_admin), int(user.is_approved),
                user.ui_language, user.last_seen_at,
                int(user.email_enabled), user.email_send_time,
                user.email_item_count, user.deleted_at,
                user.id,
            ),
        )

    def touch_user(self, conn: sqlite3.Connection, user_id: str) -> None:
        conn.execute(
            "UPDATE users SET last_seen_at=? WHERE id=?",
            (_now_iso(), user_id),
        )

    def get_all_users(
        self, conn: sqlite3.Connection, feed_id: str, *, include_deleted: bool = False
    ) -> list[User]:
        where = "feed_id=?"
        if not include_deleted:
            where += " AND deleted_at IS NULL"
        rows = conn.execute(
            f"SELECT * FROM users WHERE {where} ORDER BY created_at DESC",
            (feed_id,),
        ).fetchall()
        return [_row_to_user(r) for r in rows]

    def get_approved_email_users(
        self, conn: sqlite3.Connection, feed_id: str
    ) -> list[User]:
        rows = conn.execute(
            "SELECT * FROM users WHERE feed_id=? AND is_approved=1"
            " AND email_enabled=1 AND deleted_at IS NULL",
            (feed_id,),
        ).fetchall()
        return [_row_to_user(r) for r in rows]

    def get_admin_users(
        self, conn: sqlite3.Connection, feed_id: str
    ) -> list[User]:
        rows = conn.execute(
            "SELECT * FROM users WHERE feed_id=? AND is_admin=1 AND deleted_at IS NULL",
            (feed_id,),
        ).fetchall()
        return [_row_to_user(r) for r in rows]

    def soft_delete_user(self, conn: sqlite3.Connection, user_id: str) -> None:
        conn.execute(
            "UPDATE users SET deleted_at=? WHERE id=?",
            (_now_iso(), user_id),
        )
        # Anonymise feedback signals
        conn.execute(
            "UPDATE feedback SET user_id=NULL WHERE user_id=?", (user_id,)
        )
        # Delete preferences, read_log, saved_items, magic_link_tokens (by user)
        conn.execute("DELETE FROM preferences WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM read_log WHERE user_id=?", (user_id,))
        conn.execute("DELETE FROM saved_items WHERE user_id=?", (user_id,))
        conn.execute(
            "DELETE FROM magic_link_tokens WHERE email="
            "(SELECT email FROM users WHERE id=?)",
            (user_id,),
        )

    # ------------------------------------------------------------------
    # Preferences
    # ------------------------------------------------------------------

    def get_preferences(
        self, conn: sqlite3.Connection, user_id: str
    ) -> Optional[Preferences]:
        row = conn.execute(
            "SELECT * FROM preferences WHERE user_id=?", (user_id,)
        ).fetchone()
        return _row_to_preferences(row) if row else None

    def upsert_preferences(
        self, conn: sqlite3.Connection, prefs: Preferences
    ) -> None:
        conn.execute(
            """INSERT INTO preferences
               (id, user_id, feed_id, region_weights, topic_weights,
                company_boosts, keyword_boosts, keyword_blocks, updated_at, theme_color)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(user_id) DO UPDATE SET
                   region_weights=excluded.region_weights,
                   topic_weights=excluded.topic_weights,
                   company_boosts=excluded.company_boosts,
                   keyword_boosts=excluded.keyword_boosts,
                   keyword_blocks=excluded.keyword_blocks,
                   updated_at=excluded.updated_at,
                   theme_color=excluded.theme_color""",
            (
                prefs.id, prefs.user_id, prefs.feed_id,
                json.dumps(prefs.region_weights),
                json.dumps(prefs.topic_weights),
                json.dumps(prefs.company_boosts),
                json.dumps(prefs.keyword_boosts),
                json.dumps(prefs.keyword_blocks),
                prefs.updated_at,
                prefs.theme_color,
            ),
        )

    # ------------------------------------------------------------------
    # Digests
    # ------------------------------------------------------------------

    def get_digest(
        self,
        conn: sqlite3.Connection,
        feed_id: str,
        date: str,
        user_id: Optional[str] = None,
    ) -> Optional[Digest]:
        if user_id:
            row = conn.execute(
                "SELECT * FROM digests WHERE feed_id=? AND date=? AND user_id=?",
                (feed_id, date, user_id),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM digests WHERE feed_id=? AND date=? AND user_id IS NULL"
                " ORDER BY created_at DESC LIMIT 1",
                (feed_id, date),
            ).fetchone()
        return _row_to_digest(row) if row else None

    def get_latest_digest(
        self, conn: sqlite3.Connection, feed_id: str
    ) -> Optional[Digest]:
        row = conn.execute(
            "SELECT * FROM digests WHERE feed_id=? AND user_id IS NULL"
            " ORDER BY date DESC LIMIT 1",
            (feed_id,),
        ).fetchone()
        return _row_to_digest(row) if row else None

    def get_digest_dates(
        self, conn: sqlite3.Connection, feed_id: str, limit: int = 30
    ) -> list[str]:
        rows = conn.execute(
            "SELECT DISTINCT date FROM digests WHERE feed_id=? AND user_id IS NULL"
            " ORDER BY date DESC LIMIT ?",
            (feed_id, limit),
        ).fetchall()
        return [r["date"] for r in rows]

    def insert_digest(self, conn: sqlite3.Connection, digest: Digest) -> None:
        conn.execute(
            """INSERT INTO digests
               (id, feed_id, user_id, run_id, date, item_ids, cluster_map,
                total_read_time_min, item_count, created_at, email_sent_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                digest.id, digest.feed_id, digest.user_id, digest.run_id,
                digest.date,
                json.dumps(digest.item_ids),
                json.dumps(digest.cluster_map),
                digest.total_read_time_min, digest.item_count,
                digest.created_at, digest.email_sent_at,
            ),
        )

    def mark_digest_sent(
        self, conn: sqlite3.Connection, digest_id: str, sent_at: str
    ) -> None:
        conn.execute(
            "UPDATE digests SET email_sent_at=? WHERE id=?", (sent_at, digest_id)
        )

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------

    def upsert_feedback(
        self,
        conn: sqlite3.Connection,
        feed_id: str,
        user_id: str,
        item_id: str,
        signal: str,
    ) -> None:
        row = conn.execute(
            "SELECT id FROM feedback WHERE user_id=? AND item_id=?",
            (user_id, item_id),
        ).fetchone()
        if row:
            conn.execute(
                "UPDATE feedback SET signal=?, created_at=? WHERE id=?",
                (signal, _now_iso(), row["id"]),
            )
        else:
            conn.execute(
                "INSERT INTO feedback (id, feed_id, user_id, item_id, signal, created_at)"
                " VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), feed_id, user_id, item_id, signal, _now_iso()),
            )

    def get_feedback_for_user(
        self, conn: sqlite3.Connection, user_id: str
    ) -> dict[str, str]:
        """Return {item_id: signal} for this user."""
        rows = conn.execute(
            "SELECT item_id, signal FROM feedback WHERE user_id=?", (user_id,)
        ).fetchall()
        return {r["item_id"]: r["signal"] for r in rows}

    # ------------------------------------------------------------------
    # Read log
    # ------------------------------------------------------------------

    def log_read(
        self,
        conn: sqlite3.Connection,
        feed_id: str,
        user_id: str,
        item_id: str,
        source: str = "web",
    ) -> None:
        # Idempotent — don't double-insert for same user+item
        existing = conn.execute(
            "SELECT id FROM read_log WHERE user_id=? AND item_id=?",
            (user_id, item_id),
        ).fetchone()
        if not existing:
            conn.execute(
                "INSERT INTO read_log (id, feed_id, user_id, item_id, source, read_at)"
                " VALUES (?,?,?,?,?,?)",
                (str(uuid.uuid4()), feed_id, user_id, item_id, source, _now_iso()),
            )

    def get_read_item_ids(
        self, conn: sqlite3.Connection, user_id: str
    ) -> set[str]:
        rows = conn.execute(
            "SELECT item_id FROM read_log WHERE user_id=? AND pruned=0", (user_id,)
        ).fetchall()
        return {r["item_id"] for r in rows}

    def prune_old_read_log(self, conn: sqlite3.Connection) -> int:
        cur = conn.execute(
            "UPDATE read_log SET pruned=1 WHERE pruned=0"
            " AND read_at < datetime('now', '-180 days')"
        )
        deleted = conn.execute(
            "DELETE FROM read_log WHERE pruned=1 AND read_at < datetime('now', '-180 days')"
        )
        return deleted.rowcount

    # ------------------------------------------------------------------
    # Saved items
    # ------------------------------------------------------------------

    def save_item(
        self,
        conn: sqlite3.Connection,
        feed_id: str,
        user_id: str,
        item_id: str,
    ) -> bool:
        """Returns True if newly saved, False if already existed."""
        existing = conn.execute(
            "SELECT id FROM saved_items WHERE user_id=? AND item_id=?",
            (user_id, item_id),
        ).fetchone()
        if existing:
            return False
        conn.execute(
            "INSERT INTO saved_items (id, feed_id, user_id, item_id, saved_at)"
            " VALUES (?,?,?,?,?)",
            (str(uuid.uuid4()), feed_id, user_id, item_id, _now_iso()),
        )
        return True

    def unsave_item(
        self, conn: sqlite3.Connection, user_id: str, item_id: str
    ) -> bool:
        cur = conn.execute(
            "DELETE FROM saved_items WHERE user_id=? AND item_id=?",
            (user_id, item_id),
        )
        return cur.rowcount > 0

    def get_saved_item_ids(
        self, conn: sqlite3.Connection, user_id: str
    ) -> list[str]:
        rows = conn.execute(
            "SELECT item_id FROM saved_items WHERE user_id=? ORDER BY saved_at DESC",
            (user_id,),
        ).fetchall()
        return [r["item_id"] for r in rows]

    # ------------------------------------------------------------------
    # Share tokens
    # ------------------------------------------------------------------

    def create_share_token(
        self,
        conn: sqlite3.Connection,
        token: str,
        item_id: str,
        feed_id: str,
        expires_at: str,
    ) -> None:
        conn.execute(
            "INSERT OR REPLACE INTO share_tokens (token, item_id, feed_id, expires_at, created_at)"
            " VALUES (?,?,?,?,?)",
            (token, item_id, feed_id, expires_at, _now_iso()),
        )

    def get_share_token(
        self, conn: sqlite3.Connection, token: str
    ) -> Optional[dict]:
        row = conn.execute(
            "SELECT * FROM share_tokens WHERE token=?", (token,)
        ).fetchone()
        return dict(row) if row else None

    # ------------------------------------------------------------------
    # Sources
    # ------------------------------------------------------------------

    def upsert_source(self, conn: sqlite3.Connection, cfg: SourceConfig, feed_id: str) -> None:
        conn.execute(
            """INSERT INTO sources
               (id, feed_id, source_type, url, name, default_region, default_topic,
                source_weight, enabled, added_by)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                   source_type=excluded.source_type,
                   url=excluded.url,
                   name=excluded.name,
                   default_region=excluded.default_region,
                   default_topic=excluded.default_topic,
                   source_weight=excluded.source_weight,
                   enabled=excluded.enabled""",
            (
                cfg.id, feed_id, cfg.source_type, cfg.url, cfg.name,
                cfg.default_region, cfg.default_topic,
                cfg.source_weight, int(cfg.enabled), "config",
            ),
        )

    def get_sources(
        self, conn: sqlite3.Connection, feed_id: str, *, enabled_only: bool = True
    ) -> list[dict]:
        where = "feed_id=?"
        if enabled_only:
            where += " AND enabled=1"
        rows = conn.execute(
            f"SELECT * FROM sources WHERE {where} ORDER BY name", (feed_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def get_source(
        self, conn: sqlite3.Connection, source_id: str
    ) -> Optional[dict]:
        row = conn.execute(
            "SELECT * FROM sources WHERE id=?", (source_id,)
        ).fetchone()
        return dict(row) if row else None

    def update_source_fetch(
        self,
        conn: sqlite3.Connection,
        source_id: str,
        status: str,
        at: str,
    ) -> None:
        if status == "ok":
            conn.execute(
                "UPDATE sources SET last_fetch_at=?, last_fetch_status=?,"
                " consecutive_failures=0 WHERE id=?",
                (at, status, source_id),
            )
        else:
            conn.execute(
                "UPDATE sources SET last_fetch_at=?, last_fetch_status=?,"
                " consecutive_failures=consecutive_failures+1 WHERE id=?",
                (at, status, source_id),
            )

    # ------------------------------------------------------------------
    # Source health
    # ------------------------------------------------------------------

    def upsert_source_health(
        self,
        conn: sqlite3.Connection,
        health: SourceHealth,
    ) -> None:
        conn.execute(
            """INSERT INTO source_health
               (source_id, feed_id, last_ok_at, last_error_at, last_error_message,
                consecutive_failures, is_flagged)
               VALUES (?,?,?,?,?,?,?)
               ON CONFLICT(source_id) DO UPDATE SET
                   last_ok_at=excluded.last_ok_at,
                   last_error_at=excluded.last_error_at,
                   last_error_message=excluded.last_error_message,
                   consecutive_failures=excluded.consecutive_failures,
                   is_flagged=excluded.is_flagged""",
            (
                health.source_id, health.feed_id,
                health.last_ok_at, health.last_error_at, health.last_error_message,
                health.consecutive_failures, int(health.is_flagged),
            ),
        )

    def get_source_health(
        self, conn: sqlite3.Connection, feed_id: str
    ) -> list[dict]:
        rows = conn.execute(
            "SELECT sh.*, s.name, s.source_type, s.url "
            "FROM source_health sh "
            "LEFT JOIN sources s ON sh.source_id=s.id "
            "WHERE sh.feed_id=?",
            (feed_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Pipeline runs
    # ------------------------------------------------------------------

    def insert_pipeline_run(self, conn: sqlite3.Connection, run: PipelineRun) -> None:
        conn.execute(
            """INSERT INTO pipeline_runs
               (id, feed_id, started_at, finished_at, status,
                items_fetched, items_after_dedup, items_in_digest,
                total_usd, error_message, current_stage)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                run.id, run.feed_id, run.started_at, run.finished_at,
                run.status, run.items_fetched, run.items_after_dedup,
                run.items_in_digest, run.total_usd, run.error_message,
                run.current_stage,
            ),
        )

    def update_pipeline_run(self, conn: sqlite3.Connection, run: PipelineRun) -> None:
        conn.execute(
            """UPDATE pipeline_runs SET
                finished_at=?, status=?, items_fetched=?, items_after_dedup=?,
                items_in_digest=?, total_usd=?, error_message=?, current_stage=?
               WHERE id=?""",
            (
                run.finished_at, run.status, run.items_fetched,
                run.items_after_dedup, run.items_in_digest, run.total_usd,
                run.error_message, run.current_stage, run.id,
            ),
        )

    def get_pipeline_run(
        self, conn: sqlite3.Connection, run_id: str
    ) -> Optional[dict]:
        row = conn.execute(
            "SELECT * FROM pipeline_runs WHERE id=?", (run_id,)
        ).fetchone()
        return dict(row) if row else None

    def get_recent_pipeline_runs(
        self, conn: sqlite3.Connection, feed_id: str, limit: int = 7
    ) -> list[dict]:
        rows = conn.execute(
            "SELECT * FROM pipeline_runs WHERE feed_id=? ORDER BY started_at DESC LIMIT ?",
            (feed_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # LLM cost log
    # ------------------------------------------------------------------

    def insert_cost_entry(self, conn: sqlite3.Connection, entry: LlmCostEntry) -> None:
        conn.execute(
            """INSERT INTO llm_cost_log
               (id, feed_id, run_id, agent, model, prompt_name, prompt_version,
                input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                usd, called_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                entry.id, entry.feed_id, entry.run_id, entry.agent, entry.model,
                entry.prompt_name, entry.prompt_version,
                entry.input_tokens, entry.output_tokens,
                entry.cache_read_tokens, entry.cache_write_tokens,
                entry.usd, entry.called_at,
            ),
        )

    def get_cost_for_run(
        self, conn: sqlite3.Connection, run_id: str
    ) -> float:
        row = conn.execute(
            "SELECT COALESCE(SUM(usd),0) AS total FROM llm_cost_log WHERE run_id=?",
            (run_id,),
        ).fetchone()
        return row["total"] if row else 0.0

    def get_cost_for_month(
        self, conn: sqlite3.Connection, feed_id: str, year_month: str
    ) -> float:
        """year_month: 'YYYY-MM'"""
        row = conn.execute(
            "SELECT COALESCE(SUM(usd),0) AS total FROM llm_cost_log"
            " WHERE feed_id=? AND strftime('%Y-%m', called_at)=?",
            (feed_id, year_month),
        ).fetchone()
        return row["total"] if row else 0.0

    def get_cost_log(
        self,
        conn: sqlite3.Connection,
        feed_id: str,
        *,
        limit: int = 100,
        run_id: Optional[str] = None,
    ) -> list[dict]:
        where = "feed_id=?"
        params: list[Any] = [feed_id]
        if run_id:
            where += " AND run_id=?"
            params.append(run_id)
        rows = conn.execute(
            f"SELECT * FROM llm_cost_log WHERE {where}"
            f" ORDER BY called_at DESC LIMIT ?",
            params + [limit],
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Magic link tokens
    # ------------------------------------------------------------------

    def create_magic_token(
        self,
        conn: sqlite3.Connection,
        token: str,
        email: str,
        expires_at: str,
    ) -> None:
        conn.execute(
            "INSERT INTO magic_link_tokens (token, email, expires_at, used, created_at)"
            " VALUES (?,?,?,0,?)",
            (token, email, expires_at, _now_iso()),
        )

    def get_magic_token(
        self, conn: sqlite3.Connection, token: str
    ) -> Optional[dict]:
        row = conn.execute(
            "SELECT * FROM magic_link_tokens WHERE token=?", (token,)
        ).fetchone()
        return dict(row) if row else None

    def consume_magic_token(self, conn: sqlite3.Connection, token: str) -> None:
        conn.execute(
            "UPDATE magic_link_tokens SET used=1 WHERE token=?", (token,)
        )

    # ------------------------------------------------------------------
    # Watchlist (admin-managed entries)
    # ------------------------------------------------------------------

    def get_watchlist(
        self, conn: sqlite3.Connection, feed_id: str, *, enabled_only: bool = False
    ) -> list[dict]:
        where = "feed_id=?"
        if enabled_only:
            where += " AND enabled=1"
        rows = conn.execute(
            f"SELECT * FROM watchlist WHERE {where} ORDER BY name", (feed_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def upsert_watchlist_entry(
        self,
        conn: sqlite3.Connection,
        entry_id: str,
        feed_id: str,
        entry_type: str,
        name: str,
        aliases: list[str],
        boost: float,
        role: Optional[str],
        notes: Optional[str],
        enabled: bool = True,
    ) -> None:
        now = _now_iso()
        conn.execute(
            """INSERT INTO watchlist
               (id, feed_id, entry_type, name, aliases, boost, role, notes, enabled, created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id, feed_id) DO UPDATE SET
                   entry_type=excluded.entry_type,
                   name=excluded.name,
                   aliases=excluded.aliases,
                   boost=excluded.boost,
                   role=excluded.role,
                   notes=excluded.notes,
                   enabled=excluded.enabled""",
            (
                entry_id, feed_id, entry_type, name,
                json.dumps(aliases), boost, role, notes, int(enabled), now,
            ),
        )

    def delete_watchlist_entry(
        self, conn: sqlite3.Connection, entry_id: str, feed_id: str
    ) -> None:
        conn.execute(
            "DELETE FROM watchlist WHERE id=? AND feed_id=?", (entry_id, feed_id)
        )

    # ------------------------------------------------------------------
    # GDPR export
    # ------------------------------------------------------------------

    def export_user_data(
        self, conn: sqlite3.Connection, user_id: str
    ) -> dict:
        user_row = conn.execute(
            "SELECT * FROM users WHERE id=?", (user_id,)
        ).fetchone()
        if not user_row:
            return {}
        prefs_row = conn.execute(
            "SELECT * FROM preferences WHERE user_id=?", (user_id,)
        ).fetchone()
        read_rows = conn.execute(
            "SELECT item_id, source, read_at FROM read_log"
            " WHERE user_id=? AND pruned=0 ORDER BY read_at DESC",
            (user_id,),
        ).fetchall()
        fb_rows = conn.execute(
            "SELECT item_id, signal, created_at FROM feedback"
            " WHERE user_id=? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return {
            "user": {k: user_row[k] for k in user_row.keys()},
            "preferences": {k: prefs_row[k] for k in prefs_row.keys()} if prefs_row else {},
            "read_log": [dict(r) for r in read_rows],
            "feedback": [dict(r) for r in fb_rows],
            "exported_at": _now_iso(),
        }
