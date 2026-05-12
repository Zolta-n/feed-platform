"""Integration tests for CLI commands."""
import os
import pytest
from click.testing import CliRunner
from cli import cli

FEED_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "../../feeds/test-fixture")
)


def test_bundle_validate(tmp_db):
    runner = CliRunner()
    result = runner.invoke(cli, ["bundle", "validate", "--feed-dir", FEED_DIR])
    assert result.exit_code == 0, f"Output: {result.output}"
    assert "Validation passed" in result.output


def test_pipeline_run(tmp_db):
    runner = CliRunner()
    result = runner.invoke(cli, [
        "pipeline", "run",
        "--feed-dir", FEED_DIR,
        "--db-path", tmp_db,
    ])
    assert result.exit_code == 0, f"Output: {result.output}\nException: {result.exception}"
    assert "complete" in result.output.lower() or "Pipeline run" in result.output


def test_agent_fetch(tmp_db):
    runner = CliRunner()
    result = runner.invoke(cli, [
        "agent", "fetch",
        "--feed-dir", FEED_DIR,
    ])
    assert result.exit_code == 0, f"Output: {result.output}"
    assert "Total fetched:" in result.output
