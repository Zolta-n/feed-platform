"""
Integration test: full pipeline end-to-end using test-fixture bundle (EP10).

Tests:
- Full pipeline run produces a pipeline_runs record with status=complete
- Items table has rows with feed_id set
- Digest is created
- EP1: no domain strings in core/ or web/
"""
import os
import re
import uuid
import pytest

FEED_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../feeds/test-fixture")
)


def test_pipeline_end_to_end(bundle, repo):
    """Full pipeline run with stub sources produces a complete run record."""
    from niche.core.pipeline.runner import PipelineRunner

    run_id = str(uuid.uuid4())
    runner = PipelineRunner(bundle, repo, run_id=run_id)
    returned_run_id = runner.run()

    assert returned_run_id == run_id

    with repo.connect() as conn:
        run = repo.get_pipeline_run(conn, run_id)
    assert run is not None
    assert run["status"] == "complete", f"Pipeline failed: {run.get('error_message')}"
    assert run["feed_id"] == "test-fixture"
    assert run["items_fetched"] > 0


def test_items_have_feed_id(bundle, repo):
    """All items in the table must have feed_id set (EP5)."""
    from niche.core.pipeline.runner import PipelineRunner
    runner = PipelineRunner(bundle, repo)
    runner.run()

    with repo.connect() as conn:
        rows = conn.execute("SELECT id, feed_id FROM items").fetchall()
    assert len(rows) > 0
    for row in rows:
        assert row["feed_id"] == "test-fixture", f"Item {row['id']} has wrong feed_id"


def test_digest_created(bundle, repo):
    """A digest record should be created after a successful pipeline run."""
    import datetime
    from niche.core.pipeline.runner import PipelineRunner
    runner = PipelineRunner(bundle, repo)
    runner.run()

    today = datetime.date.today().isoformat()
    with repo.connect() as conn:
        digest = repo.get_digest(conn, "test-fixture", today)
    assert digest is not None
    assert digest.item_count >= 0


def test_ep1_no_domain_strings_in_core():
    """EP1: no brake-by-wire domain strings in niche/core/ or niche/web/."""
    deny_list_path = os.path.abspath(
        os.path.join(os.path.dirname(__file__),
                     "../../feeds/brake-by-wire/ci_deny_list.txt")
    )
    if not os.path.exists(deny_list_path):
        pytest.skip("ci_deny_list.txt not found; skipping EP1 check")

    with open(deny_list_path) as f:
        deny_strings = [line.strip() for line in f if line.strip() and not line.startswith("#")]

    if not deny_strings:
        pytest.skip("ci_deny_list.txt is empty")

    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "../..")
    )
    violations = []
    for check_dir in ("niche/core", "niche/web"):
        abs_dir = os.path.join(project_root, check_dir)
        for root, dirs, files in os.walk(abs_dir):
            dirs[:] = [d for d in dirs if d != "__pycache__"]
            for fname in files:
                if not fname.endswith(".py"):
                    continue
                fpath = os.path.join(root, fname)
                with open(fpath) as f:
                    for lineno, line in enumerate(f, 1):
                        for ds in deny_strings:
                            if ds.lower() in line.lower():
                                violations.append(
                                    f"{fpath}:{lineno}: '{ds}' found"
                                )
    assert not violations, "EP1 violations:\n" + "\n".join(violations)
