"""Runs the relay worker's Node tests (relay/worker.js against a fake GitHub API)."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_relay_worker():
    r = subprocess.run(["node", str(ROOT / "tests" / "relay.test.mjs")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
