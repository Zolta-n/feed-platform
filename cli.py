"""
Main CLI entry point for the Niche feed platform.

Usage:
    python cli.py pipeline run --feed-dir feeds/brake-by-wire
    python cli.py agent fetch --feed-dir feeds/brake-by-wire
    python cli.py bundle validate --feed-dir feeds/brake-by-wire
    python cli.py admin promote --email user@example.com
"""
import logging
import os
import sys

import click

# Load .env in development
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

logging.basicConfig(
    level=logging.INFO,
    format='{"time":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","msg":%(message)s}',
)


@click.group()
def cli():
    """Niche feed platform CLI."""


# ── pipeline ────────────────────────────────────────────────────────────────

@cli.group()
def pipeline():
    """Pipeline commands."""


@pipeline.command("run")
@click.option("--feed-dir", required=True, help="Path to feed bundle directory")
@click.option("--db-path", default=None, help="Path to SQLite database")
@click.option("--run-id", default=None, help="Pipeline run ID (UUID; generated if omitted)")
def pipeline_run(feed_dir: str, db_path: str, run_id: str):
    """Run the full pipeline for a feed bundle."""
    import uuid
    from niche.core.bundle_loader import load_bundle
    from niche.core.models.repository import Repository
    from niche.core.models.schema import init_db
    from niche.core.pipeline.runner import PipelineRunner

    db = db_path or os.environ.get("NICHE_DB_PATH", "niche.db")
    init_db(db)
    bundle = load_bundle(feed_dir)
    repo = Repository(db)

    # Sync sources
    with repo.connect() as conn:
        for src_cfg in bundle.sources:
            repo.upsert_source(conn, src_cfg, bundle.config.feed_id)

    runner = PipelineRunner(bundle, repo, run_id=run_id or str(uuid.uuid4()))
    final_run_id = runner.run()
    click.echo(f"Pipeline run complete. run_id={final_run_id}")


# ── agent ────────────────────────────────────────────────────────────────────

@cli.group()
def agent():
    """Individual agent commands."""


@agent.command("fetch")
@click.option("--feed-dir", required=True)
@click.option("--db-path", default=None)
def agent_fetch(feed_dir: str, db_path: str):
    """Run the fetch agent and print item count."""
    import json
    from niche.core.bundle_loader import load_bundle
    from niche.core.sources.factory import build_sources
    from niche.core.sources.retry import fetch_with_retry

    bundle = load_bundle(feed_dir)
    sources = build_sources(bundle.sources, bundle)
    total = 0
    for source in sources:
        items = fetch_with_retry(source.source_id, source.fetch)
        click.echo(f"  {source.source_id}: {len(items)} items")
        total += len(items)
    click.echo(f"Total fetched: {total}")


@agent.command("classify")
@click.option("--feed-dir", required=True)
@click.option("--db-path", default=None)
@click.option("--run-id", default=None)
def agent_classify(feed_dir: str, db_path: str, run_id: str):
    """Run the classify agent on items from the latest run."""
    db = db_path or os.environ.get("NICHE_DB_PATH", "niche.db")
    from niche.core.bundle_loader import load_bundle
    from niche.core.models.repository import Repository
    from niche.core.pipeline.classify import classify

    bundle = load_bundle(feed_dir)
    repo = Repository(db)
    with repo.connect() as conn:
        items = repo.get_items(conn, bundle.config.feed_id,
                               run_id=run_id, exclude_duplicates=True, limit=200)
    items = classify(items, bundle)
    with repo.connect() as conn:
        for item in items:
            repo.update_item(conn, item)
    click.echo(f"Classified {len(items)} items")


@agent.command("summarize")
@click.option("--feed-dir", required=True)
@click.option("--db-path", default=None)
@click.option("--run-id", default=None)
def agent_summarize(feed_dir: str, db_path: str, run_id: str):
    """Run the summarize agent on items from the latest run."""
    db = db_path or os.environ.get("NICHE_DB_PATH", "niche.db")
    from niche.core.bundle_loader import load_bundle
    from niche.core.models.repository import Repository
    from niche.core.pipeline.summarize import summarize

    bundle = load_bundle(feed_dir)
    repo = Repository(db)
    with repo.connect() as conn:
        items = repo.get_items(conn, bundle.config.feed_id,
                               run_id=run_id, exclude_duplicates=True, limit=200)
    items = summarize(items, bundle)
    with repo.connect() as conn:
        for item in items:
            repo.update_item(conn, item)
    click.echo(f"Summarized {sum(1 for i in items if i.summary)} items")


@agent.command("rank")
@click.option("--feed-dir", required=True)
@click.option("--db-path", default=None)
@click.option("--run-id", default=None)
def agent_rank(feed_dir: str, db_path: str, run_id: str):
    """Run the rank agent."""
    db = db_path or os.environ.get("NICHE_DB_PATH", "niche.db")
    from niche.core.bundle_loader import load_bundle
    from niche.core.models.repository import Repository
    from niche.core.pipeline.rank import rank

    bundle = load_bundle(feed_dir)
    repo = Repository(db)
    with repo.connect() as conn:
        items = repo.get_items(conn, bundle.config.feed_id,
                               run_id=run_id, exclude_duplicates=True, limit=200)
    ranked = rank(items, bundle)
    with repo.connect() as conn:
        for item in ranked:
            repo.update_item(conn, item)
    click.echo(f"Ranked {len(ranked)} items")


@agent.command("send")
@click.option("--feed-dir", required=True)
@click.option("--db-path", default=None)
def agent_send(feed_dir: str, db_path: str):
    """Send the latest digest email to all approved users."""
    db = db_path or os.environ.get("NICHE_DB_PATH", "niche.db")
    import datetime
    from niche.core.bundle_loader import load_bundle
    from niche.core.models.repository import Repository
    click.echo("Email send agent: not fully implemented (requires email provider config).")


# ── bundle ───────────────────────────────────────────────────────────────────

@cli.group()
def bundle():
    """Feed bundle commands."""


@bundle.command("validate")
@click.option("--feed-dir", required=True, help="Path to feed bundle directory")
def bundle_validate(feed_dir: str):
    """Validate a feed bundle directory."""
    from niche.core.bundle_loader import BundleValidationError, load_bundle
    from niche.core.sources.factory import SOURCE_REGISTRY

    try:
        b = load_bundle(feed_dir)
        click.echo(f"Bundle '{b.config.feed_id}' loaded successfully.")
        click.echo(f"  Sources: {len(b.sources)}")
        click.echo(f"  Watchlist: {len(b.watchlist)}")
        click.echo(f"  Prompts: {list(b.prompts.keys())}")
        click.echo(f"  Topics: {[t.id for t in b.taxonomy.topics]}")

        # Check source types are registered
        unknown_types = {
            s.source_type for s in b.sources
            if s.source_type not in SOURCE_REGISTRY
        }
        if unknown_types:
            click.echo(f"  WARNING: Unknown source types: {unknown_types}", err=True)
        else:
            click.echo("  All source types registered.")

        click.echo("Validation passed.")
    except BundleValidationError as exc:
        click.echo(f"Validation FAILED: {exc}", err=True)
        sys.exit(1)


# ── admin ────────────────────────────────────────────────────────────────────

@cli.group()
def admin():
    """Admin commands."""


@admin.command("promote")
@click.option("--email", required=True, help="User email to promote to admin")
@click.option("--db-path", default=None)
@click.option("--feed-dir", default=None)
def admin_promote(email: str, db_path: str, feed_dir: str):
    """Promote a user to admin role."""
    db = db_path or os.environ.get("NICHE_DB_PATH", "niche.db")
    from niche.core.models.repository import Repository

    repo = Repository(db)
    with repo.connect() as conn:
        user = repo.get_user_by_email(conn, email)
    if not user:
        click.echo(f"User '{email}' not found.", err=True)
        sys.exit(1)
    user.is_admin = True
    user.is_approved = True
    with repo.connect() as conn:
        repo.update_user(conn, user)
    click.echo(f"User '{email}' promoted to admin.")


if __name__ == "__main__":
    cli()
