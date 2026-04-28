from __future__ import annotations

import json

from flask import Blueprint, abort, current_app, render_template
from flask_login import current_user, login_required

bp = Blueprint("digest", __name__)


@bp.route("/")
@login_required
def index():
    repo = current_app.config["REPO"]
    bundle = current_app.config["BUNDLE"]

    digest_row = repo.get_latest_digest(bundle.config.feed_id)
    if not digest_row:
        return render_template("digest/empty.html")

    return _render_digest(digest_row, repo, bundle)


@bp.route("/digest/<date>")
@login_required
def by_date(date: str):
    repo = current_app.config["REPO"]
    bundle = current_app.config["BUNDLE"]

    digest_row = repo.get_digest_by_date(bundle.config.feed_id, date)
    if not digest_row:
        abort(404)

    return _render_digest(digest_row, repo, bundle)


@bp.route("/item/<item_id>")
@login_required
def item_detail(item_id: str):
    repo = current_app.config["REPO"]
    row = repo.get_item(item_id)
    if not row:
        abort(404)

    repo.mark_item_read(row["feed_id"], current_user.id, item_id)

    company_tags = json.loads(row["company_tags"] or "[]")
    return render_template("digest/item.html", item=row, company_tags=company_tags)


def _render_digest(digest_row, repo, bundle):
    item_ids = json.loads(digest_row["item_ids"] or "[]")
    cluster_map = json.loads(digest_row["cluster_map"] or "[]")
    items = repo.get_items_by_ids(item_ids)

    read_ids = set()
    if current_user.is_authenticated:
        read_ids = repo.get_read_item_ids(current_user.id, item_ids)

    items_by_id = {r["id"]: r for r in items}
    clusters = []
    seen = set()
    for cluster in cluster_map:
        cluster_items = [
            items_by_id[iid] for iid in cluster.get("item_ids", [])
            if iid in items_by_id
        ]
        clusters.append({"label": cluster.get("label", ""), "cards": cluster_items})
        seen.update(iid for iid in cluster.get("item_ids", []))

    ungrouped = [r for r in items if r["id"] not in seen]
    if ungrouped:
        clusters.append({"label": "More", "cards": ungrouped})

    all_topics = {r["topic_tag"] for r in items if r["topic_tag"]}
    nav_tabs = [t for t in bundle.taxonomy.nav_tabs]

    return render_template(
        "digest/index.html",
        digest=digest_row,
        clusters=clusters,
        read_ids=read_ids,
        nav_tabs=nav_tabs,
        all_topics=all_topics,
    )
