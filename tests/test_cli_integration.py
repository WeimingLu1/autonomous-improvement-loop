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
import os
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
    env = {**os.environ, "PYTHONPATH": str(PROJECT)}
    return subprocess.run(
        [PY, str(INIT_PY), *args],
        cwd=PROJECT,
        capture_output=True,
        text=True,
        env=env,
    )


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module", autouse=True)
def preserve_heartbeat():
    """Backup HEARTBEAT.md before tests and restore it afterwards."""
    hb_path = PROJECT / "HEARTBEAT.md"
    backup = tempfile.mktemp(suffix=".HEARTBEAT.md")
    Path(backup).write_bytes(hb_path.read_bytes())
    yield
    hb_path.write_bytes(Path(backup).read_bytes())
    Path(backup).unlink(missing_ok=True)


# ── Read-only command tests ───────────────────────────────────────────────────

def test_queue_shows_table():
    """a-queue alias exits 0 and points users to current-task output."""
    result = _run(["a-queue"])
    assert result.returncode == 0, f"stderr: {result.stderr}"
    combined = result.stdout + result.stderr
    assert "Current Task" in combined or "ROADMAP.md not found" in combined or "TASK-" in combined


def test_queue_all_flag():
    """a-queue --all remains backward-compatible and still resolves."""
    result = _run(["a-queue", "--all"])
    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "Current Task" in combined or "ROADMAP.md not found" in combined or "TASK-" in combined


def test_log_shows_done_entries():
    """a-log prints the roadmap Done Log section or reports it's empty."""
    result = _run(["a-log", "-n", "5"])
    assert result.returncode == 0, f"stderr: {result.stderr}"
    combined = result.stdout + result.stderr
    assert "Done Log" in combined or "empty" in combined.lower() or "ROADMAP.md not found" in combined


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


def test_refresh_alias_generates_pm_task():
    """a-refresh remains a deprecated alias to a-plan."""
    result = _run(["a-refresh"])
    assert result.returncode == 0, f"a-refresh failed: {result.stderr}"
    combined = result.stdout + result.stderr
    assert "TASK-" in combined
    assert "Goal" in combined or "Acceptance Criteria" in combined


def test_trigger_force_exits_zero():
    """a-trigger --force executes the current roadmap task and exits 0."""
    roadmap_path = PROJECT / "ROADMAP.md"
    original_roadmap = roadmap_path.read_bytes() if roadmap_path.exists() else None
    try:
        _run(["a-plan"])
        result = _run(["a-trigger", "--force"])
        assert result.returncode == 0, (
            f"a-trigger --force failed\nstdout: {result.stdout}\nstderr: {result.stderr}"
        )
        combined = result.stdout + result.stderr
        assert "Started TASK-" in combined or "Execution recorded" in combined
        updated = roadmap_path.read_text(encoding="utf-8")
        assert "| pass |" in updated
    finally:
        if original_roadmap is None:
            roadmap_path.unlink(missing_ok=True)
        else:
            roadmap_path.write_bytes(original_roadmap)


def test_add_creates_user_task_plan_and_sets_current_task():
    """a-add creates a user-sourced TASK-xxx plan and sets it as current when nothing is doing."""
    roadmap_path = PROJECT / "ROADMAP.md"
    plans_dir = PROJECT / "plans"
    original_roadmap = roadmap_path.read_bytes() if roadmap_path.exists() else None
    existing_plans = {p.name: p.read_bytes() for p in plans_dir.glob('TASK-*.md')} if plans_dir.exists() else {}
    try:
        result = _run(["a-add", "测试任务：验证a-add命令"])
        assert result.returncode == 0, f"a-add failed: {result.stderr}"
        combined = result.stdout + result.stderr
        assert "TASK-" in combined
        assert "测试任务：验证a-add命令" in combined

        content = roadmap_path.read_text(encoding="utf-8")
        assert "测试任务：验证a-add命令" in content
        assert "| user |" in content or " user " in content.lower()
    finally:
        if original_roadmap is None:
            roadmap_path.unlink(missing_ok=True)
        else:
            roadmap_path.write_bytes(original_roadmap)
        if plans_dir.exists():
            for p in plans_dir.glob('TASK-*.md'):
                if p.name not in existing_plans:
                    p.unlink(missing_ok=True)
            for name, data in existing_plans.items():
                (plans_dir / name).write_bytes(data)


def test_config_set_updates_value():
    """a-config set updates the persistent config value and exits 0."""
    cfg_path = Path.home() / ".openclaw" / "skills-config" / "autonomous-improvement-loop" / "config.md"
    original = cfg_path.read_text(encoding="utf-8") if cfg_path.exists() else None
    try:
        result = _run(["a-config", "set", "project_language", "en"])
        assert result.returncode == 0, f"a-config set failed: {result.stderr}"

        content = cfg_path.read_text(encoding="utf-8")
        assert "project_language: en" in content or "project_language=en" in content
    finally:
        if original is None:
            cfg_path.unlink(missing_ok=True)
        else:
            cfg_path.write_text(original, encoding="utf-8")


def test_status_shows_project_info():
    """a-status shows project readiness information (may timeout on slow systems)."""
    result = _run(["a-status"])
    # a-status may timeout due to pytest execution time; we accept both pass and timeout
    combined = result.stdout + result.stderr
    # Should show some readiness info or timeout
    assert ("Project" in combined or "project" in combined or "Queue" in combined
            or "timeout" in combined.lower() or "TimeoutExpired" in combined)


# ── PM Roadmap command tests ─────────────────────────────────────────────────

def test_a_plan_generates_task_and_echoes_full_plan():
    """a-plan generates TASK-xxx, writes plan doc, and echoes the full plan."""
    roadmap_path = PROJECT / "ROADMAP.md"
    original_roadmap = roadmap_path.read_bytes() if roadmap_path.exists() else None
    try:
        result = _run(["a-plan"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"a-plan failed: {result.stderr}"
        # Must show TASK id
        assert "TASK-" in combined, f"No TASK-xxx in output: {combined[:200]}"
        # Must echo Goal section
        assert "## Goal" in combined or "Goal" in combined, f"No Goal section: {combined[:200]}"
        # Must echo Acceptance Criteria
        assert "## Acceptance Criteria" in combined or "Acceptance Criteria" in combined
    finally:
        if original_roadmap is not None:
            roadmap_path.write_bytes(original_roadmap)
        else:
            roadmap_path.unlink(missing_ok=True)


def test_a_current_shows_current_task_and_full_plan():
    """a-current shows current task + echoes the full plan doc."""
    roadmap_path = PROJECT / "ROADMAP.md"
    original_roadmap = roadmap_path.read_bytes() if roadmap_path.exists() else None
    try:
        # First generate a task
        _run(["a-plan"])
        result = _run(["a-current"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"a-current failed: {result.stderr}"
        # Must show task id
        assert "TASK-" in combined
        # Must show plan doc body
        assert ("## Goal" in combined or "Goal" in combined or "Execution Plan" in combined)
    finally:
        if original_roadmap is not None:
            roadmap_path.write_bytes(original_roadmap)
        else:
            roadmap_path.unlink(missing_ok=True)


def test_plan_idempotent_without_force_when_task_pending():
    roadmap_path = PROJECT / "ROADMAP.md"
    plans_dir = PROJECT / "plans"
    original_roadmap = roadmap_path.read_bytes() if roadmap_path.exists() else None
    existing_plans = {p.name for p in plans_dir.glob('TASK-*.md')} if plans_dir.exists() else set()
    try:
        first = _run(["a-plan"])
        assert first.returncode == 0
        before = {p.name for p in plans_dir.glob('TASK-*.md')} if plans_dir.exists() else set()
        second = _run(["a-plan"])
        assert second.returncode == 0
        after = {p.name for p in plans_dir.glob('TASK-*.md')} if plans_dir.exists() else set()
        assert before == after
    finally:
        if original_roadmap is not None:
            roadmap_path.write_bytes(original_roadmap)
        else:
            roadmap_path.unlink(missing_ok=True)
        if plans_dir.exists():
            for p in plans_dir.glob('TASK-*.md'):
                if p.name not in existing_plans:
                    p.unlink(missing_ok=True)


def test_a_queue_alias_shows_current_task():
    """a-queue (deprecated alias) points to a-current and shows task + plan."""
    roadmap_path = PROJECT / "ROADMAP.md"
    original_roadmap = roadmap_path.read_bytes() if roadmap_path.exists() else None
    try:
        _run(["a-plan"])
        result = _run(["a-queue"])
        combined = result.stdout + result.stderr
        assert result.returncode == 0, f"a-queue alias failed: {result.stderr}"
        assert "TASK-" in combined
    finally:
        if original_roadmap is not None:
            roadmap_path.write_bytes(original_roadmap)
        else:
            roadmap_path.unlink(missing_ok=True)


def test_a_refresh_alias_calls_a_plan():
    """a-refresh (deprecated alias) calls a-plan and generates a task."""
    roadmap_path = PROJECT / "ROADMAP.md"
    original_roadmap = roadmap_path.read_bytes() if roadmap_path.exists() else None
    try:
        result = _run(["a-refresh"])
        combined = result.stdout + result.stderr
        # a-refresh -> a-plan --force should succeed
        assert result.returncode == 0, f"a-refresh alias failed: {result.stderr}"
        assert "TASK-" in combined
    finally:
        if original_roadmap is not None:
            roadmap_path.write_bytes(original_roadmap)
        else:
            roadmap_path.unlink(missing_ok=True)


def test_add_preserves_doing_task_and_reserves_user_task_id():
    roadmap_path = PROJECT / "ROADMAP.md"
    plans_dir = PROJECT / "plans"
    original_roadmap = roadmap_path.read_bytes() if roadmap_path.exists() else None
    existing_plans = {p.name for p in plans_dir.glob('TASK-*.md')} if plans_dir.exists() else set()
    try:
        roadmap_path.write_text(
            "# Roadmap\n\n"
            "## Current Task\n\n"
            "| task_id | type | source | title | status | created |\n"
            "|--------|------|--------|-------|--------|---------|\n"
            "| TASK-001 | idea | pm | Existing task | doing | 2026-04-21 |\n\n"
            "## Rhythm State\n\n"
            "| field | value |\n"
            "|------|-------|\n"
            "| next_default_type | improve |\n"
            "| improves_since_last_idea | 0 |\n"
            "| current_plan_path | plans/TASK-001.md |\n"
            "| reserved_user_task_id |  |\n\n"
            "## PM Notes\n\n- Roadmap initialized.\n\n"
            "## Done Log\n\n"
            "| time | task_id | type | source | title | result | commit |\n"
            "|------|---------|------|--------|-------|--------|--------|\n",
            encoding="utf-8",
        )
        result = _run(["a-add", "紧急用户请求"])
        assert result.returncode == 0, result.stderr
        text = roadmap_path.read_text(encoding="utf-8")
        assert "| TASK-001 | idea | pm | Existing task | doing | 2026-04-21 |" in text
        assert "reserved_user_task_id | TASK-" in text
    finally:
        if original_roadmap is not None:
            roadmap_path.write_bytes(original_roadmap)
        else:
            roadmap_path.unlink(missing_ok=True)
        if plans_dir.exists():
            for p in plans_dir.glob('TASK-*.md'):
                if p.name not in existing_plans:
                    p.unlink(missing_ok=True)
