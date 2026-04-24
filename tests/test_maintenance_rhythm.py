"""Regression tests for maintenance rhythm bugs.

BUG 1 (cmd_plan single-task): When post_feature_maintenance_remaining=0 and consumed=False,
the current code produces `0 - 1 if False else 0 = 0` (correct). But the formula is still
wrong conceptually — it unconditionally decrements even when consumed=False but
maintenance_remaining=0. The correct fix: only decrement when both consumed=True AND
maintenance_remaining > 0.

BUG 2 (cmd_plan multi-task): Similar formula uses `any_consumed and maintenance_remaining > 0`
which IS correct. Multi-task is already fine.

FIX: Change single-task formula to: maintenance_remaining = roadmap.post_feature_maintenance_remaining - 1
if (consumed and roadmap.post_feature_maintenance_remaining > 0) else roadmap.post_feature_maintenance_remaining
"""
from pathlib import Path
import subprocess, sys

PROJECT = Path(__file__).resolve().parents[1]
INIT_PY = PROJECT / "scripts" / "init.py"
PY = sys.executable


def _run(args: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess:
    env = {**__import__("os").environ, "PYTHONPATH": str(PROJECT)}
    return subprocess.run(
        [PY, str(INIT_PY), *args],
        cwd=cwd or PROJECT,
        capture_output=True,
        text=True,
        env=env,
    )


def test_cmd_plan_does_not_decrement_maintenance_when_zero(tmp_path: Path):
    """When post_feature_maintenance_remaining=0, a-plan must NOT go negative."""
    # Setup a minimal project structure
    plans_dir = tmp_path / ".ail" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    roadmap_path = tmp_path / ".ail" / "ROADMAP.md"
    roadmap_path.parent.mkdir(parents=True, exist_ok=True)

    # Write a roadmap with maintenance_remaining=0 and a current task
    roadmap_path.write_text(
        "# Roadmap\n\n"
        "## Current Task\n\n"
        "| task_id | type | source | title | priority | status | created |\n"
        "|--------|------|--------|-------|----------|--------|---------|\n"
        "| TASK-000 | idea | pm | Previous Task | P1 | done | 2026-04-01 |\n\n"
        "## Rhythm State\n\n"
        "| field | value |\n"
        "|------|-------|\n"
        "| next_default_type | idea |\n"
        "| improves_since_last_idea | 0 |\n"
        "| post_feature_maintenance_remaining | 0 |\n"
        "| maintenance_anchor_title |  |\n"
        "| current_plan_path |  |\n"
        "| reserved_user_task_id |  |\n\n"
        "## Done Log\n\n"
        "| time | task_id | type | source | title | result | commit |\n"
        "|------|---------|------|--------|-------|--------|--------|\n",
        encoding="utf-8",
    )

    # Create PROJECT.md so task planner has project context
    (tmp_path / "PROJECT.md").write_text("# TestProject\n\nTest", encoding="utf-8")

    # Run a-plan --force (skip the "current task exists" check)
    result = _run(["a-plan", "--force"], cwd=tmp_path)

    # Must succeed
    assert result.returncode == 0, f"a-plan failed: {result.stderr}"

    # Read the updated roadmap
    text = roadmap_path.read_text(encoding="utf-8")

    # post_feature_maintenance_remaining should still be 0 (not -1)
    import re
    m = re.search(r"post_feature_maintenance_remaining\s*\|\s*(\d+)", text)
    assert m is not None, "Could not find maintenance_remaining in updated roadmap"
    val = int(m.group(1))
    assert val == 0, f"Bug: maintenance_remaining went from 0 to {val} (expected 0)"


def test_cmd_plan_maintenance_decrements_correctly_when_remaining_gt_zero():
    """When maintenance_remaining > 0 and consumed=True, it should decrement by 1."""
    # This is the correct behavior that was already working.
    # We test it to document the expected behavior.
    from scripts.roadmap import RoadmapState, CurrentTask, init_roadmap, set_current_task, load_roadmap
    from scripts.task_planner import choose_next_task
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        p = Path(td)
        roadmap_path = p / ".ail" / "ROADMAP.md"
        roadmap_path.parent.mkdir(parents=True, exist_ok=True)
        init_roadmap(roadmap_path)
        (p / "PROJECT.md").write_text("# Test\n\nTest", encoding="utf-8")

        # Set maintenance_remaining=2 (simulating after a PM idea task)
        set_current_task(
            roadmap_path,
            CurrentTask("TASK-001", "idea", "pm", "Test Idea", "P1", "doing", "2026-04-01"),
            plan_path="plans/TASK-001.md",
            next_default_type="improve",
            improves_since_last_idea=0,
            post_feature_maintenance_remaining=2,
            maintenance_anchor_title="Test Idea",
            reserved_user_task_id="",
        )

        rm = load_roadmap(roadmap_path)
        assert rm.post_feature_maintenance_remaining == 2

        # _generate_next_task will be called (maintenance remaining > 0)
        # and it should produce a maintenance task
        from scripts.cli import _generate_next_task
        _generate_next_task(p, roadmap_path, rm)

        updated = load_roadmap(roadmap_path)
        # Should have decremented from 2 to 1
        assert updated.post_feature_maintenance_remaining == 1, (
            f"Expected 1, got {updated.post_feature_maintenance_remaining}"
        )
        # And should be a maintenance task
        assert "回归验证" in updated.current_task.title or "补测试" in updated.current_task.title