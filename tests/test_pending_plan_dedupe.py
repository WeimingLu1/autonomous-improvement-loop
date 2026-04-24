"""Regression tests for pending plan title dedup bug.

BUG: _collect_pending_plan_titles() was not filtering plan titles that appeared
in the Done Log. This caused duplicate plan files to accumulate (518 duplicates
out of 567 plans) because:
1. A task gets done (title in Done Log, plan file still exists)
2. _collect_pending_plan_titles returns the done title again as "pending"
3. forbidden_titles gets the duplicate title added
4. choose_next_task generates a new plan with the same title
5. Repeat → exponential plan file growth

FIX: _collect_pending_plan_titles now accepts done_log_titles as a filter parameter
and excludes titles already in the Done Log from the pending set.
"""
from pathlib import Path

from scripts.cli import (
    _collect_pending_plan_titles,
    _collect_done_task_ids,
    _collect_done_log_titles,
)


def test_collect_pending_plan_titles_excludes_done_log_titles(tmp_path: Path):
    """A plan file whose title is in the Done Log must NOT appear as pending."""
    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    roadmap_path = tmp_path / "ROADMAP.md"

    # Create a plan file with title "Done Task"
    plan_path = plans_dir / "TASK-001.md"
    plan_path.write_text("# TASK-001 · Done Task\n\ncontent", encoding="utf-8")

    # Create a Done Log containing that title (but task_id is NOT TASK-001)
    roadmap_path.write_text(
        "# Roadmap\n\n"
        "## Done Log\n\n"
        "| time | task_id | type | source | title | result | commit |\n"
        "|------|---------|------|--------|-------|--------|--------|\n"
        "| 2026-01-01T00:00:00Z | TASK-999 | idea | pm | Done Task | pass | abc123 |\n",
        encoding="utf-8",
    )

    done_task_ids = _collect_done_task_ids(roadmap_path)
    done_log_titles = _collect_done_log_titles(roadmap_path)
    done_titles: set[str] = set()

    pending = _collect_pending_plan_titles(plans_dir, done_task_ids, done_log_titles, done_titles)

    # "Done Task" is in Done Log → must NOT be in pending set
    assert "Done Task" not in pending, (
        f"Bug: title '{'Done Task'}' is in Done Log but appears in pending plan titles"
    )


def test_collect_pending_plan_titles_excludes_current_done_titles_set(tmp_path: Path):
    """A plan whose title is in the in-progress done_titles set must be excluded."""
    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()

    plan_path = plans_dir / "TASK-002.md"
    plan_path.write_text("# TASK-002 · In Progress Task\n\ncontent", encoding="utf-8")

    done_task_ids: set[str] = set()
    done_log_titles: set[str] = set()
    done_titles = {"In Progress Task"}  # title already completed in this batch

    pending = _collect_pending_plan_titles(plans_dir, done_task_ids, done_log_titles, done_titles)

    assert "In Progress Task" not in pending


def test_collect_pending_plan_titles_includes_truly_pending(tmp_path: Path):
    """A plan with a new title (not in Done Log, not in done_titles) must be pending."""
    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    roadmap_path = tmp_path / "ROADMAP.md"

    plan_path = plans_dir / "TASK-003.md"
    plan_path.write_text("# TASK-003 · Brand New Task\n\ncontent", encoding="utf-8")

    roadmap_path.write_text(
        "# Roadmap\n\n"
        "## Done Log\n\n"
        "| time | task_id | type | source | title | result | commit |\n"
        "|------|---------|------|--------|-------|--------|--------|\n"
        "| 2026-01-01T00:00:00Z | TASK-999 | idea | pm | Some Other Task | pass | abc123 |\n",
        encoding="utf-8",
    )

    done_task_ids = _collect_done_task_ids(roadmap_path)
    done_log_titles = _collect_done_log_titles(roadmap_path)
    done_titles: set[str] = set()

    pending = _collect_pending_plan_titles(plans_dir, done_task_ids, done_log_titles, done_titles)

    assert "Brand New Task" in pending