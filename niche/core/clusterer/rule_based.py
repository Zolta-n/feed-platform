from __future__ import annotations

import json
import logging
from collections import defaultdict

import anthropic

from niche.core.models.types import Cluster, FeedBundle, Item

logger = logging.getLogger(__name__)

_TARGET_MIN = 1
_TARGET_MAX = 5
_MIN_CLUSTER_SIZE = 2


def build_clusters(
    items: list[Item],
    bundle: FeedBundle,
    client: anthropic.Anthropic | None = None,
    repo=None,
    run_id: str | None = None,
) -> list[Cluster]:
    if not items:
        return []

    raw_groups = _rule_group(items)
    merged = _merge_singletons_and_cap(raw_groups)
    merged.sort(key=lambda g: -sum(i.relevance_score for i in g))

    labels = _generate_labels(merged, bundle, client, repo, run_id)

    clusters: list[Cluster] = []
    for order, (group, label) in enumerate(zip(merged, labels)):
        clusters.append(Cluster(
            label=label,
            item_ids=[i.id for i in group],
            display_order=order,
        ))
    return clusters


def _rule_group(items: list[Item]) -> list[list[Item]]:
    """Group by topic_tag; sub-group items with overlapping company tags."""
    by_topic: dict[str, list[Item]] = defaultdict(list)
    for item in items:
        by_topic[item.topic_tag or "__none__"].append(item)

    groups: list[list[Item]] = []
    for topic_items in by_topic.values():
        no_company = [i for i in topic_items if not i.company_tags]
        with_company = [i for i in topic_items if i.company_tags]
        groups.extend(_company_overlap_groups(with_company))
        if no_company:
            groups.append(no_company)
    return groups


def _company_overlap_groups(items: list[Item]) -> list[list[Item]]:
    """Union-find grouping: items sharing any company tag belong to one group."""
    if not items:
        return []
    ungrouped = list(items)
    groups: list[list[Item]] = []
    while ungrouped:
        seed = ungrouped.pop(0)
        group = [seed]
        group_companies: set[str] = set(seed.company_tags)
        changed = True
        while changed:
            changed = False
            remaining: list[Item] = []
            for item in ungrouped:
                if set(item.company_tags) & group_companies:
                    group.append(item)
                    group_companies |= set(item.company_tags)
                    changed = True
                else:
                    remaining.append(item)
            ungrouped = remaining
        groups.append(group)
    return groups


def _merge_singletons_and_cap(groups: list[list[Item]]) -> list[list[Item]]:
    """Move singletons to a catch-all; merge smallest groups until ≤ _TARGET_MAX."""
    catch_all: list[Item] = []
    multi: list[list[Item]] = []
    for g in groups:
        if len(g) < _MIN_CLUSTER_SIZE:
            catch_all.extend(g)
        else:
            multi.append(g)
    if catch_all:
        multi.append(catch_all)

    while len(multi) > _TARGET_MAX:
        multi.sort(key=len)
        merged = multi[0] + multi[1]
        multi = [merged] + multi[2:]

    return multi


def _generate_labels(
    groups: list[list[Item]],
    bundle: FeedBundle,
    client: anthropic.Anthropic | None,
    repo,
    run_id: str | None,
) -> list[str]:
    """One Sonnet call; falls back to topic_tag labels on any failure."""
    if client is None or not groups:
        return _fallback_labels(groups)

    prompt_body = bundle.prompts.get("cluster", "")
    static_part = prompt_body.split("{{")[0].strip() if prompt_body else (
        "Generate a short thematic label (3-6 words) for each article group. "
        "Return JSON: {\"labels\": [...]}"
    )

    cluster_descriptions: list[str] = []
    for idx, group in enumerate(groups):
        titles = "\n".join(f"  - {i.title}" for i in group[:3])
        cluster_descriptions.append(f"Group {idx + 1}:\n{titles}")
    user_msg = "\n\n".join(cluster_descriptions)

    model = bundle.prompt_meta.get("cluster", {}).get("model", "claude-sonnet-4-6")
    prompt_version = bundle.prompt_meta.get("cluster", {}).get("version")

    try:
        response = client.messages.create(
            model=model,
            max_tokens=256,
            system=[{"type": "text", "text": static_part, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user_msg}],
        )
        text = _strip_fence(response.content[0].text.strip())
        data = json.loads(text)
        labels = data.get("labels", [])
        if isinstance(labels, list) and len(labels) == len(groups):
            if repo and run_id and groups:
                from niche.core.cost.tracker import record_call
                usage = response.usage
                record_call(
                    repo,
                    feed_id=groups[0][0].feed_id,
                    run_id=run_id,
                    agent="cluster",
                    model=model,
                    prompt_name="cluster",
                    prompt_version=prompt_version,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                    cache_write_tokens=getattr(usage, "cache_creation_input_tokens", 0) or 0,
                )
            return [str(label) for label in labels]
    except Exception as exc:
        logger.warning("cluster label generation failed: %s — using fallback labels", exc)

    return _fallback_labels(groups)


def _strip_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        start = 1
        end = len(lines) - 1 if lines and lines[-1].strip() == "```" else len(lines)
        text = "\n".join(lines[start:end]).strip()
    return text


def _fallback_labels(groups: list[list[Item]]) -> list[str]:
    labels: list[str] = []
    for group in groups:
        topic = group[0].topic_tag if group else "general"
        labels.append((topic or "general").replace("-", " ").title())
    return labels
