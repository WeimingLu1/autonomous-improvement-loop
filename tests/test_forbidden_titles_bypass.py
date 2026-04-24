"""Regression test: forbidden_titles must include ALL done_titles, not just done_log_titles.

ROOT CAUSE: done_titles is collected from Done Log + git history + benchmarks.
forbidden_titles only used done_log_titles. Titles completed via git history
were not in forbidden_titles, so choose_next_task could return them after clearing
done_titles in its retry path, causing duplicate plan files.

FIX: forbidden_titles.update(done_titles) so ALL completed titles are blocked.
"""
from pathlib import Path
from unittest.mock import patch

from scripts.cli import _collect_forbidden_titles
from scripts.roadmap import init_roadmap, set_current_task, load_roadmap, CurrentTask


def test_forbidden_titles_includes_done_titles_from_git_history(tmp_path: Path):
    """done_titles from git history (not in done_log) must be in forbidden_titles."""
    project = tmp_path
    plans_dir = project / ".ail" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    roadmap_path = project / ".ail" / "ROADMAP.md"
    roadmap_path.parent.mkdir(parents=True, exist_ok=True)
    (project / "PROJECT.md").write_text("# Test\n\ntest", encoding="utf-8")

    init_roadmap(roadmap_path)
    set_current_task(
        roadmap_path,
        CurrentTask("TASK-001", "idea", "pm", "Git-Completed Task", "P1", "doing", "2026-04-01"),
        plan_path="plans/TASK-001.md",
        next_default_type="idea",
        improves_since_last_idea=0,
        post_feature_maintenance_remaining=0,
        maintenance_anchor_title="",
        reserved_user_task_id="",
    )

    roadmap = load_roadmap(roadmap_path)

    # Simulate done_titles containing a title from git history (not in done_log)
    # done_log_titles does NOT have "Git-Completed Task"
    done_titles = {"Git-Completed Task"}  # from git history, NOT done_log

    forbidden_titles = _collect_forbidden_titles(
        project, roadmap_path, plans_dir, roadmap, done_titles
    )

    # After the fix, done_titles items must also be in forbidden_titles
    assert "Git-Completed Task" in forbidden_titles, (
        "Bug: done_titles entry not in forbidden_titles — "
        "titles completed via git history bypass the duplicate filter"
    )


def test_pending_plan_title_still_forbidden_after_done_titles_update(tmp_path: Path):
    """Adding done_titles to forbidden_titles must not break pending plan title filtering."""
    project = tmp_path
    plans_dir = project / ".ail" / "plans"
    plans_dir.mkdir(parents=True, exist_ok=True)
    roadmap_path = project / ".ail" / "ROADMAP.md"
    roadmap_path.parent.mkdir(parents=True, exist_ok=True)
    (project / "PROJECT.md").write_text("# Test\n\ntest", encoding="utf-8")

    # Write a pending plan file (not in done_log, not in done_titles)
    plan_path = plans_dir / "TASK-002.md"
    plan_path.write_text("# TASK-002 · Pending Plan Task\n\ncontent", encoding="utf-8")

    init_roadmap(roadmap_path)
    roadmap = load_roadmap(roadmap_path)

    # done_titles is empty (nothing completed yet)
    done_titles: set[str] = set()

    forbidden_titles = _collect_forbidden_titles(
        project, roadmap_path, plans_dir, roadmap, done_titles
    )

    # Pending plan title must be in forbidden_titles
    assert "Pending Plan Task" in forbidden_titles, (
        "Bug: pending plan title not in forbidden_titles"
    )