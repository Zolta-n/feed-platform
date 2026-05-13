from __future__ import annotations

import os
import re

import yaml

from niche.core.models.types import (
    CompanyConfig,
    FeedBundle,
    FeedConfig,
    FiltersConfig,
    FiltersRule,
    ItemTypeConfig,
    NavTab,
    RegionConfig,
    SourceConfig,
    TaxonomyConfig,
    TopicConfig,
)

_VALID_MATCH_FIELDS = {"title", "body"}

REQUIRED_PROMPT_NAMES = [
    "summarize",
    "classify-topic",
    "classify-item-type",
    "why-it-matters",
    "translate",
]

REQUIRED_PROMPT_META_KEYS = {"name", "version", "model", "last_updated"}


class BundleValidationError(Exception):
    pass


def load_bundle(feed_dir: str) -> FeedBundle:
    feed_dir = os.path.abspath(feed_dir)
    _assert_dir(feed_dir)

    config = _load_config(feed_dir)
    taxonomy = _load_taxonomy(feed_dir)
    sources = _load_sources(feed_dir, config.feed_id)
    companies = _load_watchlist(feed_dir)
    prompts, prompt_meta = _load_prompts(feed_dir)
    filters = _load_filters(feed_dir)

    return FeedBundle(
        config=config,
        taxonomy=taxonomy,
        sources=sources,
        companies=companies,
        prompts=prompts,
        prompt_meta=prompt_meta,
        feed_dir=feed_dir,
        filters=filters,
    )


def validate_bundle(feed_dir: str) -> None:
    """Raises BundleValidationError with a descriptive message if the bundle is invalid."""
    from niche.core.sources.factory import SOURCE_REGISTRY

    bundle = load_bundle(feed_dir)

    # feed_id matches directory name
    dirname = os.path.basename(os.path.abspath(feed_dir))
    if bundle.config.feed_id != dirname:
        raise BundleValidationError(
            f"feed_id '{bundle.config.feed_id}' does not match directory name '{dirname}'"
        )

    # all source types are registered
    for src in bundle.sources:
        if src.source_type not in SOURCE_REGISTRY:
            raise BundleValidationError(
                f"Source '{src.id}' has unknown type '{src.source_type}'. "
                f"Registered types: {list(SOURCE_REGISTRY)}"
            )

    # all required prompts present
    for name in REQUIRED_PROMPT_NAMES:
        if name not in bundle.prompts:
            raise BundleValidationError(f"Missing required prompt: '{name}'")


# --- private helpers ---

def _assert_dir(path: str) -> None:
    if not os.path.isdir(path):
        raise BundleValidationError(f"Feed directory not found: {path}")


def _load_config(feed_dir: str) -> FeedConfig:
    data = _read_yaml(feed_dir, "config.yaml")
    required = ["feed_id", "name", "tagline", "accent_color", "ui_languages",
                "default_ui_language", "timezone", "daily_run_time", "from_email"]
    _check_required_keys(data, required, "config.yaml")
    return FeedConfig(
        feed_id=data["feed_id"],
        name=data["name"],
        tagline=data["tagline"],
        accent_color=data["accent_color"],
        logo_path=data.get("logo_path"),
        ui_languages=tuple(data["ui_languages"]),
        default_ui_language=data["default_ui_language"],
        timezone=data["timezone"],
        daily_run_time=data["daily_run_time"],
        from_email=data["from_email"],
    )


def _load_taxonomy(feed_dir: str) -> TaxonomyConfig:
    data = _read_yaml(feed_dir, "taxonomy.yaml")
    _check_required_keys(data, ["topics", "regions", "item_types", "nav_tabs"], "taxonomy.yaml")
    return TaxonomyConfig(
        topics=tuple(
            TopicConfig(id=t["id"], label=t["label"], weight=float(t.get("weight", 1.0)))
            for t in data["topics"]
        ),
        regions=tuple(RegionConfig(id=r["id"], label=r["label"]) for r in data["regions"]),
        item_types=tuple(
            ItemTypeConfig(id=it["id"], label=it["label"], badge_color=it.get("badge_color", "#888888"))
            for it in data["item_types"]
        ),
        nav_tabs=tuple(NavTab(id=nt["id"], label=nt["label"]) for nt in data["nav_tabs"]),
    )


def _load_sources(feed_dir: str, feed_id: str) -> tuple[SourceConfig, ...]:
    data = _read_yaml(feed_dir, "sources.yaml")
    if "sources" not in data:
        raise BundleValidationError("sources.yaml: missing 'sources' key")
    configs = []
    for s in data["sources"]:
        _check_required_keys(s, ["id", "type", "name"], f"sources.yaml entry '{s.get('id', '?')}'")
        configs.append(
            SourceConfig(
                id=s["id"],
                feed_id=feed_id,
                source_type=s["type"],
                url=s.get("url"),
                name=s["name"],
                default_region=s.get("default_region"),
                default_topic=s.get("default_topic"),
                source_weight=float(s.get("source_weight", 1.0)),
                enabled=bool(s.get("enabled", True)),
                item_selector=s.get("item_selector"),
                title_selector=s.get("title_selector"),
                link_selector=s.get("link_selector"),
                date_selector=s.get("date_selector"),
            )
        )
    return tuple(configs)


def _load_watchlist(feed_dir: str) -> tuple[CompanyConfig, ...]:
    data = _read_yaml(feed_dir, "watchlist.yaml")
    if "companies" not in data:
        raise BundleValidationError("watchlist.yaml: missing 'companies' key")
    companies = []
    for c in data["companies"]:
        _check_required_keys(c, ["id", "name", "value_chain_role"], f"watchlist.yaml entry '{c.get('id', '?')}'")
        companies.append(
            CompanyConfig(
                id=c["id"],
                name=c["name"],
                value_chain_role=c["value_chain_role"],
                relationships=tuple(c.get("relationships", [])),
                aliases=tuple(c.get("aliases", [])),
                boost=float(c.get("boost", 1.0)),
            )
        )
    return tuple(companies)


def _load_filters(feed_dir: str) -> FiltersConfig | None:
    path = os.path.join(feed_dir, "filters.yaml")
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise BundleValidationError("filters.yaml: expected a YAML mapping")

    block = _build_filter_rule(data.get("block"), "block")
    require_any = _build_filter_rule(data.get("require_any"), "require_any")
    max_age_days = _parse_max_age_days(data.get("max_age_days"))
    return FiltersConfig(block=block, require_any=require_any, max_age_days=max_age_days)


def _parse_max_age_days(value) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or value <= 0:
        raise BundleValidationError(
            f"filters.yaml: max_age_days must be a positive int, got {value!r}"
        )
    return value


def _build_filter_rule(rule_data: dict | None, name: str) -> FiltersRule | None:
    if not rule_data:
        return None
    phrases_raw = rule_data.get("phrases") or []
    if not phrases_raw:
        return None
    match_fields = tuple(rule_data.get("match_fields") or ["title"])
    invalid = [f for f in match_fields if f not in _VALID_MATCH_FIELDS]
    if invalid:
        raise BundleValidationError(
            f"filters.yaml [{name}]: invalid match_fields {invalid}; "
            f"allowed: {sorted(_VALID_MATCH_FIELDS)}"
        )
    phrases = tuple(str(p) for p in phrases_raw)
    compiled = tuple(
        re.compile(rf"\b{re.escape(p)}\b", re.IGNORECASE) for p in phrases
    )
    return FiltersRule(phrases=phrases, match_fields=match_fields, compiled=compiled)


def _load_prompts(feed_dir: str) -> tuple[dict[str, str], dict[str, dict]]:
    prompts_dir = os.path.join(feed_dir, "prompts")
    if not os.path.isdir(prompts_dir):
        raise BundleValidationError(f"Missing prompts/ directory in {feed_dir}")

    prompts: dict[str, str] = {}
    prompt_meta: dict[str, dict] = {}

    for filename in os.listdir(prompts_dir):
        if not filename.endswith(".md"):
            continue
        path = os.path.join(prompts_dir, filename)
        body, meta = _parse_prompt_file(path)
        name = meta["name"]
        prompts[name] = body
        prompt_meta[name] = meta

    for required in REQUIRED_PROMPT_NAMES:
        if required not in prompts:
            raise BundleValidationError(f"Missing required prompt file for '{required}' in {prompts_dir}")

    return prompts, prompt_meta


def _parse_prompt_file(path: str) -> tuple[str, dict]:
    with open(path, encoding="utf-8") as f:
        content = f.read()

    match = re.match(r"^---\n(.*?)\n---\n(.*)", content, re.DOTALL)
    if not match:
        raise BundleValidationError(f"Prompt file missing front-matter: {path}")

    try:
        meta = yaml.safe_load(match.group(1))
    except yaml.YAMLError as e:
        raise BundleValidationError(f"Invalid YAML front-matter in {path}: {e}") from e

    missing = REQUIRED_PROMPT_META_KEYS - set(meta or {})
    if missing:
        raise BundleValidationError(f"Prompt {path} missing front-matter keys: {missing}")

    body = match.group(2).strip()
    return body, meta


def _read_yaml(feed_dir: str, filename: str) -> dict:
    path = os.path.join(feed_dir, filename)
    if not os.path.isfile(path):
        raise BundleValidationError(f"Missing required file: {path}")
    with open(path, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise BundleValidationError(f"{filename}: expected a YAML mapping, got {type(data).__name__}")
    return data


def _check_required_keys(data: dict, keys: list[str], context: str) -> None:
    missing = [k for k in keys if k not in data]
    if missing:
        raise BundleValidationError(f"{context}: missing required keys: {missing}")
