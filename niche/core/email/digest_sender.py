from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def send_digest(bundle, repo, email_provider, app_url: str) -> int:
    """Send today's digest to all eligible users. Returns count of emails sent.

    Skips users with email_enabled=0 or no approved status. Skips the digest
    if email_sent_at is already set (prevents double-send on same digest).
    """
    digest_row = repo.get_latest_digest(bundle.config.feed_id)
    if not digest_row:
        logger.info("feed=%s no digest found, skipping email send", bundle.config.feed_id)
        return 0

    if digest_row["email_sent_at"]:
        logger.info(
            "feed=%s digest=%s already sent at %s, skipping",
            bundle.config.feed_id, digest_row["id"], digest_row["email_sent_at"],
        )
        return 0

    item_ids = json.loads(digest_row["item_ids"] or "[]")
    cluster_map = json.loads(digest_row["cluster_map"] or "[]")
    items = repo.get_items_by_ids(item_ids)
    items_by_id = {r["id"]: r for r in items}

    clusters = []
    seen: set[str] = set()
    for cluster in cluster_map:
        cards = [
            items_by_id[iid] for iid in cluster.get("item_ids", [])
            if iid in items_by_id
        ]
        if cards:
            clusters.append({"label": cluster.get("label", ""), "cards": cards})
            seen.update(iid for iid in cluster.get("item_ids", []))

    ungrouped = [r for r in items if r["id"] not in seen]
    if ungrouped:
        clusters.append({"label": "More", "cards": ungrouped})

    users = repo.get_all_users(bundle.config.feed_id)
    eligible = [u for u in users if u["is_approved"] and u["email_enabled"] and not u["deleted_at"]]

    if not eligible:
        logger.info("feed=%s no eligible recipients", bundle.config.feed_id)
        return 0

    sent = 0
    for user in eligible:
        try:
            _send_to_user(
                user=user,
                digest_row=digest_row,
                clusters=clusters,
                bundle=bundle,
                email_provider=email_provider,
                app_url=app_url,
            )
            sent += 1
        except Exception as exc:
            logger.error("feed=%s failed to send digest to user=%s: %s", bundle.config.feed_id, user["id"], exc)

    now = datetime.now(timezone.utc).isoformat()
    repo._conn.execute(
        "UPDATE digests SET email_sent_at=? WHERE id=?", (now, digest_row["id"])
    )
    repo._conn.commit()

    logger.info("feed=%s digest=%s sent to %d/%d users", bundle.config.feed_id, digest_row["id"], sent, len(eligible))
    return sent


def _send_to_user(*, user, digest_row, clusters, bundle, email_provider, app_url: str) -> None:
    from flask import render_template
    from niche.web.auth.magic_link import make_unsubscribe_token
    import os

    secret = os.environ.get("APPROVAL_SECRET", "dev-approval-secret")
    unsub_token = make_unsubscribe_token(user["id"], secret)
    unsubscribe_url = f"{app_url}/auth/unsubscribe/{unsub_token}"

    html = render_template(
        "email/digest.html",
        feed_name=bundle.config.name,
        tagline=bundle.config.tagline,
        accent_color=bundle.config.accent_color,
        digest_date=digest_row["date"],
        item_count=digest_row["item_count"],
        read_time_min=digest_row["total_read_time_min"],
        clusters=clusters,
        app_url=app_url,
        unsubscribe_url=unsubscribe_url,
    )

    email_provider.send(
        to=user["email"],
        subject=f"{bundle.config.name} — {digest_row['date']}",
        html=html,
        from_email=bundle.config.from_email,
    )
