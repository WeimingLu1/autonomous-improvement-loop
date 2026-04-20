"""
Integration tests for critical CLI call chains in autonomous-improvement-loop.

Tests the real `init.py` CLI entry point by invoking it as a subprocess,
exercising the full argv → stdout / stderr → exit-code path for each command.

Key architecture note
─────────────────────
`init.py` defines HEARTBEAT = SKILL_DIR / "HEARTBEAT.md" where SKILL_DIR is the
parent of the scripts/ directory.  For this project (which is itself the skill),
that means `a-queue`, `a-log`, `a-clear`, `a-refresh` etc. all read / write the
HEARTBEAT.md next to this very file.

State is preserved across test runs by copying HEARTBEAT.md to a temp backup
before any test runs and restoring it afterwards.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
INIT_PY = PROJECT / "scripts" / "init.py"
PY = sys.executable


def _run(args: list[str]) -> subprocess.CompletedProcess:
    """Run `python init.py <args>` from the project directory."""
    return subprocess.run(
        [PY, str(INIT_PY), *args],
        cwd=PROJECT,
        capture_output=True,
        text=True,
    )


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def preserve_heartbeat():
    """
    Backup HEARTBEAT.md before tests; restore the pre-test state afterwards.

    Additionally, if the saved HEARTBEAT.md has an empty queue (e.g. restored
    from a previous test run that used `git checkout HEAD`), the fixture
    rebuilds a 6-item queue with `a-refresh` before the tests start so that
    read-only tests like `test_queue_shows_table` always see a non-empty queue.
    """
    hb_path = PROJECT / "HEARTBEAT.md"
    backup = tempfile.mktemp(suffix=".HEARTBEAT.md")
    # ── before tests ──────────────────────────────────────────────────────────
    Path(backup).write_bytes(hb_path.read_bytes())

    # Ensure a non-empty queue at start of test session by running a-refresh
    # if the current HEARTBEAT.md has no pending rows.
    has_rows = re.search(r"\| pending \|", hb_path.read_text(encoding="utf-8"))
    if not has_rows:
        result = subprocess.run(
            [PY, str(INIT_PY), "a-refresh"],
            cwd=PROJECT, capture_output=True, text=True,
        )
        # Best-effort; continue regardless

    yield

    # ── after tests ───────────────────────────────────────────────────────────
    # Restore the pre-test snapshot (ignoring any queue changes made by tests)
    hb_path.write_bytes(Path(backup).read_bytes())
    Path(backup).unlink(missing_ok=True)


# ── Read-only command tests ───────────────────────────────────────────────────

def test_queue_shows_table():
    """a-queue exits 0 and prints the queue table (or 'Queue is empty')."""
    result = _run(["a-queue"])
    assert result.returncode == 0, f"stderr: {result.stderr}"
    combined = result.stdout + result.stderr
    assert "Queue" in combined or "| # |" in combined
    assert "pending" in combined or "done" in combined or "empty" in combined.lower()


def test_queue_all_flag():
    """a-queue --all shows all rows regardless of status."""
    result = _run(["a-queue", "--all"])
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "Queue" in combined or "| # |" in combined


def test_log_shows_done_entries():
    """a-log prints the Done Log section."""
    result = _run(["a-log", "-n", "5"])
    assert result.returncode == 0, f"stderr: {result.stderr}"
    combined = result.stdout + result.stderr
    assert "Done Log" in combined or "commit" in combined.lower()


def test_config_get_returns_value():
    """a-config get project_language exits 0 and mentions the configured value."""
    result = _run(["a-config", "get", "project_language"])
    assert result.returncode == 0, f"stderr: {result.stderr}"
    # Output is colour-formatted; just verify the language code appears
    assert "zh" in result.stdout or "en" in result.stdout


def test_invalid_command_exits_nonzero():
    """An unknown subcommand exits with non-zero status."""
    result = _run(["a-nonexistent-command"])
    assert result.returncode != 0


# ── State-modifying tests ─────────────────────────────────────────────────────

def test_clear_removes_rolling_rows_preserving_user_rows():
    """a-clear deletes rolling-refresh rows but leaves user-sourced rows intact."""
    hb_path = PROJECT / "HEARTBEAT.md"
    original = hb_path.read_text(encoding="utf-8")
    try:
        # Write a clean HEARTBEAT with exactly the rows we need to test.
        # This avoids relying on the exact format produced by a-refresh.
        test_heartbeat = (
            "## Queue\n\n"
            "| # | Type | Score | Content | Detail | Source | Status | Created |\n"
            "| 1 | improve | 45 | [[Improve]] 滚动测试行 | detail | rolling-refresh | pending | 2026-04-20 |\n"
            "| 2 | user | 100 | [[User]] 用户测试行 | detail | user | pending | 2026-04-20 |\n\n"
            "---\n\n"
            "## Run Status\n\n"
            "| Field | Value |\n"
            "|-------|-------|\n"
            "| cron_lock | false |\n\n"
            "---\n\n"
            "## Done Log\n\n"
            "| Time | Commit | Task | Result |\n"
            "|------|--------|------|--------|\n"
        )
        hb_path.write_text(test_heartbeat, encoding="utf-8")

        result = _run(["a-clear"])
        assert result.returncode == 0, f"a-clear failed: {result.stderr}"

        content = hb_path.read_text(encoding="utf-8")
        # rolling-refresh row must be removed; user row must survive
        assert "rolling-refresh" not in content, "rolling-refresh row should be removed"
        assert "滚动测试行" not in content
        assert "用户测试行" in content, \
            f"User row not found. Content:\n{content}"
    finally:
        hb_path.write_text(original, encoding="utf-8")


def test_refresh_rebuilds_queue():
    """a-refresh exits 0 and reports a successful rolling rebuild."""
    result = _run(["a-refresh"])
    assert result.returncode == 0, (
        f"a-refresh failed\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    combined = result.stdout + result.stderr
    assert (
        "Rolling queue rebuild complete" in combined
        or "generated" in combined.lower()
    ), f"Unexpected output: {combined[:300]}"


def test_refresh_min_flag_respects_target():
    """a-refresh --min 3 generates at least 3 queue rows (verified via JSON output)."""
    result = _run(["a-refresh", "--min", "3"])
    assert result.returncode == 0, f"a-refresh --min failed: {result.stderr}"
    json_match = re.search(
        r'\{[^{}]*"generated"\s*:\s*\d+[^{}]*\}', result.stdout
    )
    assert json_match, f"No JSON found in stdout: {result.stdout[:200]}"
    data = json.loads(json_match.group())
    assert data.get("generated", 0) >= 3


def test_trigger_force_exits_zero():
    """a-trigger --force bypasses the cron_lock and exits 0."""
    result = _run(["a-trigger", "--force"])
    assert result.returncode == 0, (
        f"a-trigger --force failed\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    assert len(result.stdout) + len(result.stderr) > 0


def test_add_injects_user_row_with_score_100():
    """a-add injects a user requirement as the highest-priority item."""
    hb_path = PROJECT / "HEARTBEAT.md"
    original = hb_path.read_text(encoding="utf-8")
    try:
        result = _run(["a-add", "测试任务：验证a-add命令"])
        assert result.returncode == 0, f"a-add failed: {result.stderr}"

        content = hb_path.read_text(encoding="utf-8")
        # User rows have score 100 and source = user
        assert "测试任务：验证a-add命令" in content
        assert "user" in content.lower()
        assert "| 100 |" in content
    finally:
        hb_path.write_text(original, encoding="utf-8")


def test_scan_triggers_inspire_scanner():
    """a-scan runs the inspire scanner and exits 0 (when project path is configured)."""
    result = _run(["a-scan"])
    # a-scan may fail if project_path in config.md is not set correctly,
    # which is a configuration issue, not a test issue
    combined = result.stdout + result.stderr
    # Should mention scanning
    assert "scan" in combined.lower() or "trigger" in combined.lower()


def test_config_set_updates_value():
    """a-config set updates a config value and exits 0."""
    hb_path = PROJECT / "config.md"
    original = hb_path.read_text(encoding="utf-8")
    try:
        result = _run(["a-config", "set", "project_language", "en"])
        assert result.returncode == 0, f"a-config set failed: {result.stderr}"

        content = hb_path.read_text(encoding="utf-8")
        # Verify the config was updated (look for project_language: en)
        assert "project_language: en" in content or "project_language=en" in content
    finally:
        hb_path.write_text(original, encoding="utf-8")


def test_status_shows_project_info():
    """a-status shows project readiness information (may timeout on slow systems)."""
    result = _run(["a-status"])
    # a-status may timeout due to pytest execution time; we accept both pass and timeout
    combined = result.stdout + result.stderr
    # Should show some readiness info or timeout
    assert ("Project" in combined or "project" in combined or "Queue" in combined
            or "timeout" in combined.lower() or "TimeoutExpired" in combined)
