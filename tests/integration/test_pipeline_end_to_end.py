from __future__ import annotations

import os
import re
import uuid

import pytest


def test_pipeline_runs_to_completion(bundle, repo):
    from niche.core.pipeline.runner import run_pipeline

    run_id = str(uuid.uuid4())
    results = run_pipeline(bundle, repo, run_id)

    # pipeline returned stage results
    stage_names = {r.stage for r in results}
    assert "fetch" in stage_names
    assert "dedup" in stage_names
    assert "compose" in stage_names

    # pipeline_runs record written with correct status
    row = repo._conn.execute(
        "SELECT status, feed_id FROM pipeline_runs WHERE id=?", (run_id,)
    ).fetchone()
    assert row is not None
    assert row["status"] == "complete"
    assert row["feed_id"] == "test-fixture"

    # items written to DB
    items = repo._conn.execute(
        "SELECT id, feed_id FROM items WHERE run_id=?", (run_id,)
    ).fetchall()
    assert len(items) > 0, "Expected items to be written to DB"

    # every item has feed_id set (EP5)
    for item in items:
        assert item["feed_id"] == "test-fixture", f"Item {item['id']} missing feed_id"

    # digest written
    digest = repo._conn.execute(
        "SELECT * FROM digests WHERE run_id=?", (run_id,)
    ).fetchone()
    assert digest is not None
    assert digest["feed_id"] == "test-fixture"
    assert digest["item_count"] > 0


def test_ep1_no_domain_strings_in_core(feed_dir):
    """
    EP1: No domain strings from ci_deny_list.txt appear in niche/core/ or niche/web/.
    """
    deny_list_path = os.path.join(feed_dir, "ci_deny_list.txt")
    assert os.path.isfile(deny_list_path), "ci_deny_list.txt not found in test-fixture"

    with open(deny_list_path) as f:
        deny_terms = [line.strip() for line in f if line.strip()]

    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
    scan_dirs = [
        os.path.join(repo_root, "niche", "core"),
        os.path.join(repo_root, "niche", "web"),
    ]

    violations: list[str] = []
    for scan_dir in scan_dirs:
        for dirpath, _, filenames in os.walk(scan_dir):
            for filename in filenames:
                if not filename.endswith(".py"):
                    continue
                filepath = os.path.join(dirpath, filename)
                with open(filepath, encoding="utf-8") as f:
                    for lineno, line in enumerate(f, 1):
                        for term in deny_terms:
                            if term in line:
                                rel = os.path.relpath(filepath, repo_root)
                                violations.append(f"{rel}:{lineno}: contains '{term}'")

    assert not violations, (
        "EP1 violation — domain strings found in core/web code:\n"
        + "\n".join(violations)
    )


def test_two_runs_dedup_correctly(bundle, repo):
    """Second run with the same stub items should mark all as duplicates."""
    from niche.core.pipeline.runner import run_pipeline

    run_id_1 = str(uuid.uuid4())
    run_pipeline(bundle, repo, run_id_1)

    run_id_2 = str(uuid.uuid4())
    run_pipeline(bundle, repo, run_id_2)

    # Items from second run should be marked as duplicates
    dupes = repo._conn.execute(
        "SELECT COUNT(*) as n FROM items WHERE run_id=? AND is_duplicate=1", (run_id_2,)
    ).fetchone()["n"]
    total = repo._conn.execute(
        "SELECT COUNT(*) as n FROM items WHERE run_id=?", (run_id_2,)
    ).fetchone()["n"]

    assert total > 0
    assert dupes == total, f"Expected all {total} items in run 2 to be duplicates, got {dupes}"
