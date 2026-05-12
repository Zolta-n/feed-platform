"""
Dataclasses for the Niche feed platform.

All domain strings (feed names, company names, topic labels, source URLs)
come from feed bundles at runtime — never hardcoded here (EP1).
"""
from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from typing import Optional


# ---------------------------------------------------------------------------
# Source / fetch layer
# ---------------------------------------------------------------------------

@dataclass
class RawItem:
    """Unprocessed item returned by a Source adapter (before dedup/classify)."""
    source_id: str
    url: str
    title: str
    body: str           # raw text or HTML excerpt; may be empty
    language: str       # ISO 639-1; "en" if unknown
    published_at: Optional[datetime.datetime]
    fetched_at: datetime.datetime
    extra: dict = field(default_factory=dict)   # adapter-specific metadata


# ---------------------------------------------------------------------------
# Feed bundle configuration types
# ---------------------------------------------------------------------------

@dataclass
class FeedConfig:
    """Parsed from config.yaml."""
    feed_id: str
    name: str
    tagline: str
    accent_color: str
    logo_path: Optional[str]
    ui_languages: list[str]
    default_ui_language: str
    timezone: str
    daily_run_time: str     # "HH:MM"
    from_email: str


@dataclass
class TaxonomyTopic:
    id: str
    label: str
    weight: float = 1.0


@dataclass
class TaxonomyRegion:
    id: str
    label: str


@dataclass
class TaxonomyItemType:
    id: str
    label: str
    badge_color: str = "#888888"


@dataclass
class NavTab:
    id: str
    label: str


@dataclass
class SourceConfig:
    """One entry from sources.yaml."""
    id: str
    source_type: str        # rss / gdelt / google_news / scraper / regulatory
    name: str
    url: Optional[str] = None
    default_region: Optional[str] = None
    default_topic: Optional[str] = None
    source_weight: float = 1.0
    enabled: bool = True
    extra: dict = field(default_factory=dict)   # adapter-specific fields


@dataclass
class WatchlistEntry:
    id: str
    name: str
    aliases: list[str] = field(default_factory=list)
    boost: float = 1.5
    role: Optional[str] = None
    notes: Optional[str] = None
    enabled: bool = True
    entry_type: str = "company"


@dataclass
class PromptMeta:
    name: str
    version: int
    model: str
    last_updated: str
    max_input_tokens: int = 800
    body: str = ""          # the prompt text below the front-matter


@dataclass
class Taxonomy:
    topics: list[TaxonomyTopic] = field(default_factory=list)
    regions: list[TaxonomyRegion] = field(default_factory=list)
    item_types: list[TaxonomyItemType] = field(default_factory=list)
    nav_tabs: list[NavTab] = field(default_factory=list)


@dataclass
class FeedBundle:
    """Loaded by bundle_loader.py; everything callers need at runtime."""
    config: FeedConfig
    taxonomy: Taxonomy
    sources: list[SourceConfig]
    watchlist: list[WatchlistEntry]
    prompts: dict[str, PromptMeta]   # keyed by prompt name


# ---------------------------------------------------------------------------
# Pipeline / persistence types
# ---------------------------------------------------------------------------

@dataclass
class Item:
    """Processed item; maps 1-to-1 with the `items` table row."""
    id: str
    feed_id: str
    url: str
    url_hash: str
    title_hash: Optional[str] = None
    title: Optional[str] = None
    title_translated: Optional[str] = None
    body_raw: Optional[str] = None
    body_translated: Optional[str] = None
    summary: Optional[str] = None
    why_it_matters: Optional[str] = None
    source_id: Optional[str] = None
    source_name: Optional[str] = None
    source_language: str = "en"
    topic_tag: Optional[str] = None
    item_type: Optional[str] = None
    region_tag: Optional[str] = None
    company_tags: list[str] = field(default_factory=list)
    translation_failed: bool = False
    translation_provider: Optional[str] = None
    relevance_score: float = 0.0
    published_at: Optional[str] = None     # ISO-8601 string
    fetched_at: str = ""                   # ISO-8601 string
    run_id: Optional[str] = None
    word_count: int = 0
    read_time_min: float = 0.0
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None
    image_url: Optional[str] = None

    def company_tags_json(self) -> str:
        return json.dumps(self.company_tags)

    @classmethod
    def company_tags_from_json(cls, raw: str) -> list[str]:
        try:
            return json.loads(raw) if raw else []
        except (json.JSONDecodeError, TypeError):
            return []


@dataclass
class Cluster:
    label: str
    item_ids: list[str]
    display_order: int = 0
    lead_blurb: Optional[str] = None


@dataclass
class Digest:
    id: str
    feed_id: str
    date: str                   # YYYY-MM-DD
    item_ids: list[str]
    cluster_map: list[dict]     # serialised Cluster list
    total_read_time_min: float
    item_count: int
    created_at: str             # ISO-8601
    user_id: Optional[str] = None
    run_id: Optional[str] = None
    email_sent_at: Optional[str] = None


@dataclass
class User:
    id: str
    feed_id: str
    email: str
    is_admin: bool = False
    is_approved: bool = False
    ui_language: str = "en"
    created_at: str = ""
    last_seen_at: Optional[str] = None
    email_enabled: bool = True
    email_send_time: str = "06:30"
    email_item_count: int = 15
    deleted_at: Optional[str] = None


@dataclass
class Preferences:
    id: str
    user_id: str
    feed_id: str
    region_weights: dict = field(default_factory=dict)
    topic_weights: dict = field(default_factory=dict)
    company_boosts: dict = field(default_factory=dict)
    keyword_boosts: list = field(default_factory=list)
    keyword_blocks: list = field(default_factory=list)
    updated_at: str = ""
    theme_color: str = "red"


@dataclass
class PipelineRun:
    id: str
    feed_id: str
    started_at: str
    status: str = "running"
    finished_at: Optional[str] = None
    items_fetched: int = 0
    items_after_dedup: int = 0
    items_in_digest: int = 0
    total_usd: float = 0.0
    error_message: Optional[str] = None
    current_stage: Optional[str] = None


@dataclass
class LlmCostEntry:
    id: str
    feed_id: str
    agent: str
    model: str
    called_at: str
    run_id: Optional[str] = None
    prompt_name: Optional[str] = None
    prompt_version: Optional[int] = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    usd: float = 0.0


@dataclass
class SourceHealth:
    source_id: str
    feed_id: str
    last_ok_at: Optional[str] = None
    last_error_at: Optional[str] = None
    last_error_message: Optional[str] = None
    consecutive_failures: int = 0
    is_flagged: bool = False
