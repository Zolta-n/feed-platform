import sqlite3

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS pipeline_runs (
    id TEXT PRIMARY KEY,
    feed_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    items_fetched INTEGER DEFAULT 0,
    items_after_dedup INTEGER DEFAULT 0,
    items_in_digest INTEGER DEFAULT 0,
    total_usd REAL DEFAULT 0.0,
    error_message TEXT
);

CREATE TABLE IF NOT EXISTS sources (
    id TEXT PRIMARY KEY,
    feed_id TEXT NOT NULL,
    source_type TEXT NOT NULL,
    url TEXT,
    name TEXT NOT NULL,
    default_region TEXT,
    default_topic TEXT,
    source_weight REAL NOT NULL DEFAULT 1.0,
    enabled INTEGER NOT NULL DEFAULT 1,
    last_fetch_at TEXT,
    last_fetch_status TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    added_by TEXT NOT NULL DEFAULT 'config'
);

CREATE TABLE IF NOT EXISTS items (
    id TEXT PRIMARY KEY,
    feed_id TEXT NOT NULL,
    url TEXT NOT NULL,
    url_hash TEXT NOT NULL,
    title_hash TEXT,
    title TEXT,
    title_translated TEXT,
    body_raw TEXT,
    body_translated TEXT,
    summary TEXT,
    why_it_matters TEXT,
    source_id TEXT REFERENCES sources(id),
    source_name TEXT,
    source_language TEXT NOT NULL DEFAULT 'en',
    topic_tag TEXT,
    item_type TEXT,
    region_tag TEXT,
    company_tags TEXT NOT NULL DEFAULT '[]',
    translation_failed INTEGER NOT NULL DEFAULT 0,
    translation_provider TEXT,
    relevance_score REAL NOT NULL DEFAULT 0.0,
    published_at TEXT,
    fetched_at TEXT NOT NULL,
    run_id TEXT REFERENCES pipeline_runs(id),
    word_count INTEGER NOT NULL DEFAULT 0,
    read_time_min REAL NOT NULL DEFAULT 0.0,
    is_duplicate INTEGER NOT NULL DEFAULT 0,
    duplicate_of TEXT REFERENCES items(id)
);

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    feed_id TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    is_approved INTEGER NOT NULL DEFAULT 0,
    ui_language TEXT NOT NULL DEFAULT 'en',
    created_at TEXT NOT NULL,
    last_seen_at TEXT,
    email_enabled INTEGER NOT NULL DEFAULT 1,
    email_send_time TEXT NOT NULL DEFAULT '06:30',
    email_item_count INTEGER NOT NULL DEFAULT 15,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS preferences (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id),
    feed_id TEXT NOT NULL,
    region_weights TEXT NOT NULL DEFAULT '{}',
    topic_weights TEXT NOT NULL DEFAULT '{}',
    company_boosts TEXT NOT NULL DEFAULT '{}',
    keyword_boosts TEXT NOT NULL DEFAULT '[]',
    keyword_blocks TEXT NOT NULL DEFAULT '[]',
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS digests (
    id TEXT PRIMARY KEY,
    feed_id TEXT NOT NULL,
    user_id TEXT REFERENCES users(id),
    run_id TEXT REFERENCES pipeline_runs(id),
    date TEXT NOT NULL,
    item_ids TEXT NOT NULL DEFAULT '[]',
    cluster_map TEXT NOT NULL DEFAULT '[]',
    total_read_time_min REAL NOT NULL DEFAULT 0.0,
    item_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    email_sent_at TEXT
);

CREATE TABLE IF NOT EXISTS feedback (
    id TEXT PRIMARY KEY,
    feed_id TEXT NOT NULL,
    user_id TEXT REFERENCES users(id),
    item_id TEXT NOT NULL REFERENCES items(id),
    signal TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS read_log (
    id TEXT PRIMARY KEY,
    feed_id TEXT NOT NULL,
    user_id TEXT NOT NULL REFERENCES users(id),
    item_id TEXT NOT NULL REFERENCES items(id),
    source TEXT NOT NULL DEFAULT 'web',
    read_at TEXT NOT NULL,
    pruned INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS llm_cost_log (
    id TEXT PRIMARY KEY,
    feed_id TEXT NOT NULL,
    run_id TEXT,
    agent TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_name TEXT,
    prompt_version INTEGER,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    usd REAL NOT NULL DEFAULT 0.0,
    called_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS magic_link_tokens (
    token TEXT PRIMARY KEY,
    email TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS source_health (
    source_id TEXT PRIMARY KEY REFERENCES sources(id),
    feed_id TEXT NOT NULL,
    last_ok_at TEXT,
    last_error_at TEXT,
    last_error_message TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    is_flagged INTEGER NOT NULL DEFAULT 0
);
"""


def create_schema(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(CREATE_TABLES)
    conn.commit()
