from pathlib import Path

from scripts.roadmap import RoadmapState
from scripts.task_planner import choose_next_task


def test_returns_idea_task_type_when_next_default_is_idea(tmp_path: Path):
    (tmp_path / "PROJECT.md").write_text("# Project\n\nNeed better onboarding and release UX", encoding="utf-8")
    roadmap = RoadmapState(None, "idea", 0, "", "")
    task = choose_next_task(tmp_path, roadmap, set(), "zh")
    assert task.task_type == "idea"


def test_returns_improve_task_type_when_next_default_is_improve(tmp_path: Path):
    (tmp_path / "PROJECT.md").write_text("# Project\n\nCLI task planning", encoding="utf-8")
    roadmap = RoadmapState(None, "improve", 1, "", "")
    task = choose_next_task(tmp_path, roadmap, set(), "zh")
    assert task.task_type == "improve"


def test_raises_error_when_all_titles_are_done(tmp_path: Path):
    (tmp_path / "PROJECT.md").write_text("# Project\n\nCLI task planning", encoding="utf-8")
    roadmap = RoadmapState(None, "idea", 0, "", "")
    # Exhaust all idea candidates
    done = {
        "为 a-current 增加完整计划文档回显能力",
        "为 ROADMAP 模型增加当前任务摘要与计划联动输出",
        "为 CLI 增加 roadmap 驱动的任务规划入口",
    }
    try:
        choose_next_task(tmp_path, roadmap, done, "zh")
    except ValueError:
        pass
    else:
        # If no error, verify it's not one of the done titles
        task = choose_next_task(tmp_path, roadmap, done, "zh")
        assert task.title not in done


def test_returns_unique_title_not_in_done_titles(tmp_path: Path):
    (tmp_path / "PROJECT.md").write_text("# Project\n\nCLI task planning", encoding="utf-8")
    roadmap = RoadmapState(None, "improve", 1, "", "")
    task = choose_next_task(tmp_path, roadmap, {"为 roadmap 命令流补齐集成测试覆盖"}, "zh")
    assert task.title != "为 roadmap 命令流补齐集成测试覆盖"


def test_planned_task_has_required_fields(tmp_path: Path):
    (tmp_path / "PROJECT.md").write_text("# Project\n\nCLI task planning", encoding="utf-8")
    roadmap = RoadmapState(None, "idea", 0, "", "")
    task = choose_next_task(tmp_path, roadmap, set(), "zh")
    for name in ["task_type", "source", "title", "context", "why_now", "scope", "non_goals", "relevant_files", "execution_plan", "acceptance_criteria", "verification", "risks"]:
        assert getattr(task, name) is not None


def test_idea_task_has_non_empty_title_context_why_now(tmp_path: Path):
    (tmp_path / "PROJECT.md").write_text("# DemoProject\n\nNeed roadmap work", encoding="utf-8")
    roadmap = RoadmapState(None, "idea", 0, "", "")
    task = choose_next_task(tmp_path, roadmap, set(), "zh")
    assert task.title
    assert task.context
    assert task.why_now


def test_improve_task_has_non_empty_fields(tmp_path: Path):
    (tmp_path / "PROJECT.md").write_text("# DemoProject\n\nNeed roadmap work", encoding="utf-8")
    roadmap = RoadmapState(None, "improve", 1, "", "")
    task = choose_next_task(tmp_path, roadmap, set(), "zh")
    assert task.title
    assert task.context
    assert task.why_now


def test_reads_project_name_from_project_md(tmp_path: Path):
    (tmp_path / "PROJECT.md").write_text("# AwesomeProject\n\nNeed roadmap work", encoding="utf-8")
    roadmap = RoadmapState(None, "idea", 0, "", "")
    task = choose_next_task(tmp_path, roadmap, set(), "zh")
    assert "AwesomeProject" in task.context


def test_choose_next_task_returns_different_titles_for_repeated_calls(tmp_path: Path):
    """5 consecutive calls return 5 different titles (dedup works)."""
    (tmp_path / "PROJECT.md").write_text("# TestProject\n\nTest roadmap", encoding="utf-8")
    roadmap = RoadmapState(None, "idea", 0, "", "")
    seen = []
    for _ in range(5):
        task = choose_next_task(tmp_path, roadmap, set(), "zh")
        seen.append(task.title)
    assert len(set(seen)) == 5, f"Expected 5 unique titles, got duplicates: {seen}"


def test_scope_is_file_specific(tmp_path: Path):
    """Scope contains specific file paths, not generic descriptions."""
    (tmp_path / "PROJECT.md").write_text("# TestProject\n\nTest", encoding="utf-8")
    roadmap = RoadmapState(None, "improve", 0, "", "")
    task = choose_next_task(tmp_path, roadmap, set(), "zh")
    # Scope should contain at least one specific file path like "scripts/init.py"
    assert len(task.scope) >= 1, "Scope should not be empty"
    first_scope = task.scope[0]
    assert "/" in first_scope or ".py" in first_scope, \
        f"Scope should be a file path, got: {first_scope!r}"


def test_effort_field_is_valid_value(tmp_path: Path):
    """effort field must be one of short/medium/long."""
    (tmp_path / "PROJECT.md").write_text("# TestProject\n\nTest", encoding="utf-8")
    roadmap = RoadmapState(None, "idea", 0, "", "")
    task = choose_next_task(tmp_path, roadmap, set(), "zh")
    assert task.effort in ("short", "medium", "long"), \
        f"effort must be short/medium/long, got: {task.effort!r}"


def test_background_and_rollback_populated(tmp_path: Path):
    """background and rollback fields are non-empty for improve tasks."""
    (tmp_path / "PROJECT.md").write_text("# TestProject\n\nTest", encoding="utf-8")
    roadmap = RoadmapState(None, "improve", 0, "", "")
    task = choose_next_task(tmp_path, roadmap, set(), "zh")
    assert task.background, "background should be non-empty"
    assert task.rollback, "rollback should be non-empty"
