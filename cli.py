#!/usr/bin/env python3
"""Niche platform CLI — entry point for all agents, pipeline, and admin commands."""

from __future__ import annotations

import importlib
import json
import logging
import os
import uuid

import click


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        record.message = record.getMessage()
        return json.dumps({
            "time": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.message,
        })


_handler = logging.StreamHandler()
_handler.setFormatter(_JsonFormatter())
logging.basicConfig(level=logging.INFO, handlers=[_handler])


def _load(feed_dir: str, db_path: str | None):
    from niche.core.bundle_loader import load_bundle
    from niche.core.models.repository import Repository

    bundle = load_bundle(feed_dir)
    db = db_path or os.environ.get("NICHE_DB_PATH", "niche.db")
    repo = Repository(db)
    repo.create_schema()
    return bundle, repo


# ---------------------------------------------------------------------------
# Top-level group
# ---------------------------------------------------------------------------

@click.group()
def cli():
    """Niche feed platform CLI."""


# ---------------------------------------------------------------------------
# pipeline
# ---------------------------------------------------------------------------

@cli.group()
def pipeline():
    """Pipeline commands."""


@pipeline.command("run")
@click.option("--feed-dir", required=True, help="Path to feed bundle directory.")
@click.option("--db-path", default=None, help="Path to SQLite database.")
def pipeline_run(feed_dir: str, db_path: str | None):
    """Run the full pipeline for a feed bundle."""
    from niche.core.pipeline.runner import run_pipeline

    bundle, repo = _load(feed_dir, db_path)
    run_id = str(uuid.uuid4())
    click.echo(f"Starting pipeline run_id={run_id} feed={bundle.config.feed_id}")

    try:
        results = run_pipeline(bundle, repo, run_id)
        summary = {
            "run_id": run_id,
            "feed_id": bundle.config.feed_id,
            "stages": [
                {"stage": r.stage, "in": r.item_count_in, "out": r.item_count_out, "s": round(r.duration_s, 3)}
                for r in results
            ],
        }
        click.echo(json.dumps(summary, indent=2))
    finally:
        repo.close()


# ---------------------------------------------------------------------------
# agent
# ---------------------------------------------------------------------------

@cli.group()
def agent():
    """Run a single agent standalone."""


def _agent_cmd(name: str, module_path: str, *, pass_repo: bool = True):
    @agent.command(name)
    @click.option("--feed-dir", required=True)
    @click.option("--run-id", default=None)
    @click.option("--db-path", default=None)
    def _cmd(feed_dir, run_id, db_path):
        mod = importlib.import_module(module_path)
        bundle, repo = _load(feed_dir, db_path)
        rid = run_id or str(uuid.uuid4())
        try:
            result = mod.run(bundle, rid) if not pass_repo else mod.run(bundle, repo, rid)
            click.echo(f"agent={name} run_id={rid} result={result}")
        finally:
            repo.close()
    _cmd.__name__ = name
    return _cmd


_agent_cmd("fetch",    "niche.core.agents.fetcher",   pass_repo=False)
_agent_cmd("dedup",    "niche.core.agents.deduper")
_agent_cmd("classify", "niche.core.agents.classifier")
_agent_cmd("translate","niche.core.agents.translator")
_agent_cmd("summarize","niche.core.agents.summarizer")
_agent_cmd("rank",     "niche.core.agents.ranker")
_agent_cmd("cluster",  "niche.core.agents.clusterer")
_agent_cmd("compose",  "niche.core.agents.composer")
_agent_cmd("send",     "niche.core.agents.sender")


# ---------------------------------------------------------------------------
# bundle
# ---------------------------------------------------------------------------

@cli.group()
def bundle():
    """Feed bundle commands."""


@bundle.command("validate")
@click.option("--feed-dir", required=True)
def bundle_validate(feed_dir: str):
    """Validate a feed bundle directory."""
    from niche.core.bundle_loader import BundleValidationError, validate_bundle

    try:
        validate_bundle(feed_dir)
        click.echo(f"OK: feed bundle at '{feed_dir}' is valid.")
    except BundleValidationError as e:
        click.echo(f"ERROR: {e}", err=True)
        raise SystemExit(1) from e


# ---------------------------------------------------------------------------
# admin
# ---------------------------------------------------------------------------

@cli.group()
def admin():
    """Admin commands."""


@admin.command("promote")
@click.option("--email", required=True, help="Email address to promote to admin.")
@click.option("--feed-dir", required=True, help="Feed bundle directory (for feed_id).")
@click.option("--db-path", default=None)
def admin_promote(email: str, feed_dir: str, db_path: str | None):
    """Grant admin role to a user (creates user record if not exists)."""
    bundle, repo = _load(feed_dir, db_path)
    try:
        repo.upsert_user_admin(email, bundle.config.feed_id)
        click.echo(f"Promoted {email} to admin for feed '{bundle.config.feed_id}'.")
    finally:
        repo.close()


if __name__ == "__main__":
    cli()
