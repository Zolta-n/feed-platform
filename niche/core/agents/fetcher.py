"""Fetcher agent — wraps the fetch stage with CLI entry point."""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

import click

from ..bundle_loader import load_bundle
from ..models.types import RawItem
from ..sources.factory import build_sources
from ..sources.retry import fetch_with_retry

logger = logging.getLogger(__name__)


def run_fetch(feed_dir: str) -> list[RawItem]:
    """Fetch all items from all enabled sources in the bundle."""
    bundle = load_bundle(feed_dir)
    sources = build_sources(bundle.sources, bundle)
    raw_items: list[RawItem] = []
    for source in sources:
        items = fetch_with_retry(source.source_id, source.fetch)
        raw_items.extend(items)
        logger.info("Source %s: %d items", source.source_id, len(items))
    return raw_items


@click.command("fetch")
@click.option("--feed-dir", required=True, help="Path to feed bundle directory")
@click.option("--run-id", default=None, help="Pipeline run ID (generated if not provided)")
def fetch_cmd(feed_dir: str, run_id: Optional[str]) -> None:
    """Fetch all items from configured sources and print as JSON."""
    if not run_id:
        run_id = str(uuid.uuid4())
    items = run_fetch(feed_dir)
    output = []
    for item in items:
        output.append({
            "source_id": item.source_id,
            "url": item.url,
            "title": item.title,
            "language": item.language,
            "published_at": item.published_at.isoformat() if item.published_at else None,
        })
    click.echo(json.dumps(output, indent=2))
