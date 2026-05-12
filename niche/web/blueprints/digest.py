"""
Digest blueprint — main feed view.

Routes:
  GET /                  — redirect to today's digest
  GET /digest/<date>     — digest for a specific date
  GET /item/<item_id>    — item detail view
"""
from __future__ import annotations

import collections
import datetime
import json
import logging

from flask import (
    Blueprint, abort, current_app, redirect, render_template,
    request, url_for,
)
from flask_login import current_user, login_required

logger = logging.getLogger(__name__)

digest_bp = Blueprint("digest", __name__)


def _repo():
    return current_app.config["REPO"]


def _bundle():
    return current_app.config.get("BUNDLE")


@digest_bp.route("/")
@login_required
def index():
    today = datetime.date.today().isoformat()
    tab = request.args.get("tab", "ALL")
    date = request.args.get("date", today)
    return _render_digest(date=date, active_tab=tab)


@digest_bp.route("/digest/<date>")
@login_required
def digest_for_date(date: str):
    tab = request.args.get("tab", "ALL")
    return _render_digest(date=date, active_tab=tab)


def _render_digest(date: str, active_tab: str = "ALL"):
    repo = _repo()
    bundle = _bundle()
    feed_id = bundle.config.feed_id if bundle else "default"

    # Try to get a user-personalised digest first, then canonical
    with repo.connect() as conn:
        digest = repo.get_digest(conn, feed_id, date, current_user.id)
        if digest is None:
            digest = repo.get_digest(conn, feed_id, date)

    if digest is None:
        with repo.connect() as conn:
            available_dates = repo.get_digest_dates(conn, feed_id)
        return render_template(
            "digest/empty.html",
            date=date,
            available_dates=available_dates,
        )

    # Load items for this digest
    with repo.connect() as conn:
        items = repo.get_items_by_ids(conn, digest.item_ids)

    # Load user read/feedback/saved state
    with repo.connect() as conn:
        read_item_ids = repo.get_read_item_ids(conn, current_user.id)
        item_feedback = repo.get_feedback_for_user(conn, current_user.id)
        saved_ids = set(repo.get_saved_item_ids(conn, current_user.id))

    # Attach user feedback to each item for inline JSON
    for item in items:
        item._user_feedback = item_feedback.get(item.id)

    # Get user preferences for theme
    with repo.connect() as conn:
        prefs = repo.get_preferences(conn, current_user.id)
    theme_color = prefs.theme_color if prefs else "red"

    # Build cluster_map list: [{label, items, topic_tag, lead_blurb}]
    item_by_id = {i.id: i for i in items}
    cluster_map = []
    for cl in digest.cluster_map:
        cl_items = [item_by_id[iid] for iid in cl.get("item_ids", []) if iid in item_by_id]
        if cl_items:
            topic_tag = cl_items[0].topic_tag if cl_items else None
            cluster_map.append({
                "label": cl.get("label", ""),
                "articles": cl_items,
                "topic_tag": topic_tag,
                "lead_blurb": cl.get("lead_blurb"),
            })

    # Breaking items for ticker
    breaking_items = [i for i in items if i.item_type == "breaking"]

    # Stats
    total_items = len(items)
    total_read_time = round(digest.total_read_time_min)
    read_count = len([i for i in items if i.id in read_item_ids])

    # Pipeline run info
    pipeline_run = None
    if digest.run_id:
        with repo.connect() as conn:
            pipeline_run = repo.get_pipeline_run(conn, digest.run_id)

    # Top sources and companies
    source_counts: dict[str, int] = collections.Counter(
        i.source_name for i in items if i.source_name
    )
    top_sources = source_counts.most_common(5)

    company_counts: dict[str, int] = collections.Counter()
    for i in items:
        for c in (i.company_tags or []):
            company_counts[c] += 1
    top_companies = company_counts.most_common(5)

    # Inline JSON for JS
    items_json = json.dumps([
        {
            "id": i.id,
            "url": i.url,
            "title": i.title,
            "title_translated": i.title_translated,
            "summary": i.summary,
            "why_it_matters": i.why_it_matters,
            "source_name": i.source_name,
            "item_type": i.item_type,
            "topic_tag": i.topic_tag,
            "region_tag": i.region_tag,
            "company_tags": json.dumps(i.company_tags) if i.company_tags else "[]",
            "read_time_min": i.read_time_min,
            "published_at": i.published_at,
            "user_feedback": item_feedback.get(i.id),
        }
        for i in items
    ])

    # Available dates for nav
    with repo.connect() as conn:
        available_dates = repo.get_digest_dates(conn, feed_id)

    return render_template(
        "digest/index.html",
        digest=digest,
        items=items,
        items_json=items_json,
        cluster_map=cluster_map,
        breaking_items=breaking_items,
        active_tab=active_tab,
        read_item_ids=read_item_ids,
        item_feedback=item_feedback,
        saved_ids=saved_ids,
        date=date,
        total_items=total_items,
        total_read_time=total_read_time,
        read_count=read_count,
        pipeline_run=pipeline_run,
        top_sources=top_sources,
        top_companies=top_companies,
        available_dates=available_dates,
        theme_color=theme_color,
    )


@digest_bp.route("/item/<item_id>")
@login_required
def item_detail(item_id: str):
    """Item detail view — redirect to the digest date or render standalone."""
    repo = _repo()
    bundle = _bundle()
    feed_id = bundle.config.feed_id if bundle else "default"

    with repo.connect() as conn:
        item = repo.get_item(conn, item_id)
    if item is None or item.feed_id != feed_id:
        abort(404)

    # Log as read
    with repo.connect() as conn:
        repo.log_read(conn, feed_id, current_user.id, item_id, source="web")

    # If this item belongs to a digest, redirect there
    if item.fetched_at:
        date = item.fetched_at[:10]
        return redirect(url_for("digest.digest_for_date", date=date))

    # Fallback: redirect to today's digest
    today = datetime.date.today().isoformat()
    return redirect(url_for("digest.digest_for_date", date=today))
