"""
Feed bundle loader (EP1, EP5).

Reads the four YAML files and the prompts/ directory from a feed bundle
directory and returns a frozen FeedBundle dataclass. No raw dicts leak
out of this module.

Usage:
    bundle = load_bundle("feeds/brake-by-wire")
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import yaml

from .models.types import (
    FeedBundle, FeedConfig, NavTab, PromptMeta, SourceConfig, Taxonomy,
    TaxonomyItemType, TaxonomyRegion, TaxonomyTopic, WatchlistEntry,
)

logger = logging.getLogger(__name__)


class BundleValidationError(ValueError):
    """Raised when a required feed bundle key is missing or invalid."""


def _require(data: dict, key: str, file_hint: str) -> Any:
    if key not in data:
        raise BundleValidationError(
            f"Required key '{key}' missing in {file_hint}"
        )
    return data[key]


def _load_yaml(path: Path, name: str) -> dict:
    if not path.exists():
        raise BundleValidationError(f"Missing required file: {path}")
    with path.open() as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise BundleValidationError(f"{name} must be a YAML mapping, got {type(data)}")
    return data


_FRONT_MATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)


def _parse_prompt_file(path: Path) -> PromptMeta:
    text = path.read_text()
    m = _FRONT_MATTER_RE.match(text)
    if not m:
        raise BundleValidationError(
            f"Prompt file {path.name} is missing YAML front-matter block (---)"
        )
    fm = yaml.safe_load(m.group(1))
    for key in ("name", "version", "model", "last_updated"):
        if key not in fm:
            raise BundleValidationError(
                f"Prompt file {path.name} front-matter missing required key '{key}'"
            )
    body = text[m.end():]
    return PromptMeta(
        name=str(fm["name"]),
        version=int(fm["version"]),
        model=str(fm["model"]),
        last_updated=str(fm["last_updated"]),
        max_input_tokens=int(fm.get("max_input_tokens", 800)),
        body=body.strip(),
    )


def load_bundle(feed_dir: str | Path) -> FeedBundle:
    """Load and validate a feed bundle directory. Returns a FeedBundle."""
    root = Path(feed_dir)
    if not root.is_dir():
        raise BundleValidationError(f"Feed directory does not exist: {root}")

    # ------------------------------------------------------------------ config
    cfg_data = _load_yaml(root / "config.yaml", "config.yaml")
    feed_id = _require(cfg_data, "feed_id", "config.yaml")
    # Validate feed_id matches directory name
    if root.name != feed_id:
        raise BundleValidationError(
            f"config.yaml feed_id '{feed_id}' does not match directory name '{root.name}'"
        )
    config = FeedConfig(
        feed_id=feed_id,
        name=_require(cfg_data, "name", "config.yaml"),
        tagline=cfg_data.get("tagline", ""),
        accent_color=cfg_data.get("accent_color", "#E63946"),
        logo_path=cfg_data.get("logo_path"),
        ui_languages=cfg_data.get("ui_languages", ["en"]),
        default_ui_language=cfg_data.get("default_ui_language", "en"),
        timezone=cfg_data.get("timezone", "UTC"),
        daily_run_time=cfg_data.get("daily_run_time", "05:00"),
        from_email=cfg_data.get("from_email", "noreply@example.com"),
    )

    # --------------------------------------------------------------- taxonomy
    tax_data = _load_yaml(root / "taxonomy.yaml", "taxonomy.yaml")
    topics = [
        TaxonomyTopic(
            id=t["id"],
            label=t.get("label", t["id"]),
            weight=float(t.get("weight", 1.0)),
        )
        for t in tax_data.get("topics", [])
    ]
    regions = [
        TaxonomyRegion(id=r["id"], label=r.get("label", r["id"]))
        for r in tax_data.get("regions", [])
    ]
    item_types = [
        TaxonomyItemType(
            id=it["id"],
            label=it.get("label", it["id"]),
            badge_color=it.get("badge_color", "#888888"),
        )
        for it in tax_data.get("item_types", [])
    ]
    nav_tabs = [
        NavTab(id=nt["id"], label=nt.get("label", nt["id"]))
        for nt in tax_data.get("nav_tabs", [])
    ]
    taxonomy = Taxonomy(
        topics=topics,
        regions=regions,
        item_types=item_types,
        nav_tabs=nav_tabs,
    )

    # --------------------------------------------------------------- sources
    src_data = _load_yaml(root / "sources.yaml", "sources.yaml")
    sources = []
    for s in src_data.get("sources", []):
        sid = _require(s, "id", "sources.yaml")
        stype = _require(s, "type", f"sources.yaml[{sid}]")
        sname = _require(s, "name", f"sources.yaml[{sid}]")
        # Collect adapter-specific extra fields
        known = {"id", "type", "name", "url", "default_region", "default_topic",
                 "source_weight", "enabled"}
        extra = {k: v for k, v in s.items() if k not in known}
        sources.append(SourceConfig(
            id=sid,
            source_type=stype,
            name=sname,
            url=s.get("url"),
            default_region=s.get("default_region"),
            default_topic=s.get("default_topic"),
            source_weight=float(s.get("source_weight", 1.0)),
            enabled=bool(s.get("enabled", True)),
            extra=extra,
        ))

    # --------------------------------------------------------------- watchlist
    wl_data = _load_yaml(root / "watchlist.yaml", "watchlist.yaml")
    watchlist = []
    for c in wl_data.get("companies", []):
        watchlist.append(WatchlistEntry(
            id=_require(c, "id", "watchlist.yaml"),
            name=_require(c, "name", "watchlist.yaml"),
            aliases=c.get("aliases", []),
            boost=float(c.get("boost", 1.5)),
            role=c.get("value_chain_role"),
            notes=c.get("notes"),
            enabled=bool(c.get("enabled", True)),
            entry_type="company",
        ))

    # --------------------------------------------------------------- prompts
    prompts_dir = root / "prompts"
    prompts: dict[str, PromptMeta] = {}
    if prompts_dir.is_dir():
        for md_file in sorted(prompts_dir.glob("*.md")):
            try:
                pm = _parse_prompt_file(md_file)
                prompts[pm.name] = pm
            except BundleValidationError as exc:
                logger.warning("Prompt load warning: %s", exc)

    return FeedBundle(
        config=config,
        taxonomy=taxonomy,
        sources=sources,
        watchlist=watchlist,
        prompts=prompts,
    )
