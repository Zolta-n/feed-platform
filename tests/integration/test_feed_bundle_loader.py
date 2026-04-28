from __future__ import annotations

import subprocess
import sys


def test_bundle_validate_cli_exits_zero(feed_dir):
    """CLI bundle validate command exits 0 for valid test-fixture."""
    result = subprocess.run(
        [sys.executable, "cli.py", "bundle", "validate", "--feed-dir", feed_dir],
        capture_output=True,
        text=True,
        cwd=__import__("os").path.abspath(
            __import__("os").path.join(__import__("os").path.dirname(__file__), "../..")
        ),
    )
    assert result.returncode == 0, f"Expected exit 0, got {result.returncode}:\n{result.stderr}"
    assert "OK" in result.stdout
