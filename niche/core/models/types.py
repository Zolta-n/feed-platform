from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RawItem:
    source_id: str
    url: str
    title: str
    body: str
    language: str
    published_at: datetime | None
    fetched_at: datetime
    extra: dict = field(default_factory=dict)


@dataclass
class Item:
    id: str
    feed_id: str
    url: str
    url_hash: str
    title: str
    title_translated: str | None
    body_raw: str
    body_translated: str | None
    summary: str | None
    why_it_matters: str | None
    source_id: str
    source_name: str
    source_language: str
    topic_tag: str | None
    item_type: str | None
    region_tag: str | None
    company_tags: list[str]
    translation_failed: bool
    translation_provider: str | None
    relevance_score: float
    published_at: datetime | None
    fetched_at: datetime
    run_id: str
    word_count: int
    read_time_min: float
    is_duplicate: bool
    duplicate_of: str | None


@dataclass
class Cluster:
    label: str
    item_ids: list[str]
    display_order: int


@dataclass
class Digest:
    id: str
    feed_id: str
    user_id: str | None
    run_id: str
    date: str
    item_ids: list[str]
    cluster_map: list[dict]
    total_read_time_min: float
    item_count: int
    created_at: str
    email_sent_at: str | None


@dataclass(frozen=True)
class SourceConfig:
    id: str
    feed_id: str
    source_type: str
    url: str | None
    name: str
    default_region: str | None
    default_topic: str | None
    source_weight: float
    enabled: bool
    item_selector: str | None = None
    title_selector: str | None = None
    link_selector: str | None = None
    date_selector: str | None = None


@dataclass(frozen=True)
class TopicConfig:
    id: str
    label: str
    weight: float


@dataclass(frozen=True)
class RegionConfig:
    id: str
    label: str


@dataclass(frozen=True)
class ItemTypeConfig:
    id: str
    label: str
    badge_color: str


@dataclass(frozen=True)
class NavTab:
    id: str
    label: str


@dataclass(frozen=True)
class CompanyConfig:
    id: str
    name: str
    value_chain_role: str
    relationships: tuple[str, ...]
    aliases: tuple[str, ...]
    boost: float


@dataclass(frozen=True)
class TaxonomyConfig:
    topics: tuple[TopicConfig, ...]
    regions: tuple[RegionConfig, ...]
    item_types: tuple[ItemTypeConfig, ...]
    nav_tabs: tuple[NavTab, ...]


@dataclass(frozen=True)
class FeedConfig:
    feed_id: str
    name: str
    tagline: str
    accent_color: str
    logo_path: str | None
    ui_languages: tuple[str, ...]
    default_ui_language: str
    timezone: str
    daily_run_time: str
    from_email: str


@dataclass(frozen=True)
class FeedBundle:
    config: FeedConfig
    taxonomy: TaxonomyConfig
    sources: tuple[SourceConfig, ...]
    companies: tuple[CompanyConfig, ...]
    prompts: dict[str, str]        # name → prompt body (front-matter stripped)
    prompt_meta: dict[str, dict]   # name → {version, model, last_updated, max_input_tokens}
    feed_dir: str                  # absolute path to the feed directory
