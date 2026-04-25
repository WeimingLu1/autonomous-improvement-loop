"""Integration tests for LLM plan generation plugged into choose_next_task."""
import json
import pytest
from pathlib import Path


def test_generate_pm_plan_with_mock(monkeypatch, tmp_path):
    """LLM plan generation returns a well-formed PMPlan that can be converted to PlannedTask."""
    (tmp_path / ".ail").mkdir()
    rm = tmp_path / ".ail" / "ROADMAP.md"
    rm.write_text(
        "# Roadmap\n\n## Rhythm State\n\n| field | value |\n|------|-------|\n| next_default_type | improve |\n",
        encoding="utf-8",
    )
    (tmp_path / "PROJECT.md").write_text("# TestProj\n\nContext", encoding="utf-8")

    def mock_call(api_key, user_prompt, language):
        return json.dumps({
            "title": "Improve test coverage",
            "task_type": "improve",
            "background": "Tests are minimal",
            "goal": "Add more tests",
            "context": "Test project context",
            "scope": ["tests/"],
            "non_goals": [],
            "relevant_files": ["tests/test_a.py"],
            "execution_plan": ["Step 1: write tests"],
            "acceptance_criteria": ["Coverage > 80%"],
            "why_now": "Quality",
            "risks": "None",
            "rollback": "git revert",
        })

    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr("scripts.llm_client._call_minimax", mock_call)

    from scripts.llm_client import generate_pm_plan
    plan = generate_pm_plan(tmp_path, "zh")

    assert plan.title == "Improve test coverage"
    assert plan.task_type == "improve"
    assert plan.background == "Tests are minimal"
    assert plan.goal == "Add more tests"
    # Lists should be lists
    assert isinstance(plan.scope, list)
    assert plan.scope == ["tests/"]
    assert isinstance(plan.execution_plan, list)
    assert plan.execution_plan == ["Step 1: write tests"]
    # maintenance_tag should default to ""
    assert plan.maintenance_tag == ""


def test_plan_to_planned_task_conversion(monkeypatch, tmp_path):
    """PMPlan from LLM can be converted to PlannedTask via _plan_to_planned_task."""
    (tmp_path / ".ail").mkdir()
    rm = tmp_path / ".ail" / "ROADMAP.md"
    rm.write_text(
        "# Roadmap\n\n## Rhythm State\n\n| field | value |\n|------|-------|\n| next_default_type | improve |\n",
        encoding="utf-8",
    )
    (tmp_path / "PROJECT.md").write_text("# TestProj\n\nContext", encoding="utf-8")

    def mock_call(api_key, user_prompt, language):
        return json.dumps({
            "title": "Improve test coverage",
            "task_type": "improve",
            "background": "Tests are minimal",
            "goal": "Add more tests",
            "context": "Test project context",
            "scope": ["tests/"],
            "non_goals": ["Do not rewrite core logic"],
            "relevant_files": ["tests/test_a.py"],
            "execution_plan": ["Step 1: write tests", "Step 2: run pytest"],
            "acceptance_criteria": ["Coverage > 80%"],
            "why_now": "Quality",
            "risks": "None",
            "rollback": "git revert",
        })

    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    monkeypatch.setattr("scripts.llm_client._call_minimax", mock_call)

    from scripts.llm_client import generate_pm_plan
    from scripts.task_planner import _plan_to_planned_task, PlannedTask

    raw_plan = generate_pm_plan(tmp_path, "zh")
    planned = _plan_to_planned_task(raw_plan)

    assert isinstance(planned, PlannedTask)
    assert planned.title == "Improve test coverage"
    assert planned.task_type == "improve"
    assert planned.source == "llm"  # LLM-generated plans get source='llm'
    assert planned.effort == "medium"
    assert planned.background == "Tests are minimal"
    assert "goal" not in planned.context.lower() or "Add more tests" in planned.context
    assert planned.scope == ["tests/"]
    assert planned.non_goals == ["Do not rewrite core logic"]
    assert planned.relevant_files == ["tests/test_a.py"]
    assert planned.execution_plan == ["Step 1: write tests", "Step 2: run pytest"]
    assert planned.acceptance_criteria == ["Coverage > 80%"]
    assert planned.why_now == "Quality"
    assert planned.risks == "None"
    assert planned.rollback == "git revert"
    assert planned.verification == []  # empty list (LLM doesn't generate verification yet)


def test_choose_next_task_with_llm(monkeypatch, tmp_path):
    """choose_next_task with use_llm=True calls the LLM and returns the generated plan."""
    (tmp_path / ".ail").mkdir()
    rm = tmp_path / ".ail" / "ROADMAP.md"
    rm.write_text(
        "# Roadmap\n\n## Rhythm State\n\n| field | value |\n|------|-------|\n| next_default_type | improve |\n",
        encoding="utf-8",
    )
    (tmp_path / "PROJECT.md").write_text("# TestProj\n\nContext", encoding="utf-8")

    def mock_call(api_key, user_prompt, language):
        return json.dumps({
            "title": "LLM-generated test improvement",
            "task_type": "improve",
            "background": "Coverage is low",
            "goal": "Add more tests",
            "context": "Test project",
            "scope": ["tests/"],
            "non_goals": [],
            "relevant_files": ["tests/test_a.py"],
            "execution_plan": ["Step 1: add tests"],
            "acceptance_criteria": ["Coverage > 80%"],
            "why_now": "Quality",
            "risks": "None",
            "rollback": "git revert",
        })

    monkeypatch.setenv("MINIMAX_API_KEY", "test-key-llm")
    monkeypatch.setattr("scripts.llm_client._call_minimax", mock_call)

    from scripts.task_planner import choose_next_task, PlannedTask
    from scripts.roadmap import RoadmapState

    roadmap = RoadmapState(
        current_task=None,
        maintenance_mode=True,
        next_default_type="improve",
        improves_since_last_idea=0,
        post_feature_maintenance_remaining=0,
        maintenance_anchor_title="",
        current_plan_path="",
        reserved_user_task_id="",
    )

    planned, consumed = choose_next_task(
        tmp_path, roadmap, done_titles=set(), language="zh",
        forbidden_titles=set(), use_llm=True
    )

    assert isinstance(planned, PlannedTask)
    assert planned.title == "LLM-generated test improvement"
    assert planned.source == "llm"  # LLM path was taken
    assert planned.task_type == "improve"
    assert consumed is False


def test_choose_next_task_llm_fallback_to_pool(monkeypatch, tmp_path):
    """When LLM fails, choose_next_task falls back to the pool."""
    (tmp_path / ".ail").mkdir()
    rm = tmp_path / ".ail" / "ROADMAP.md"
    rm.write_text(
        "# Roadmap\n\n## Rhythm State\n\n| field | value |\n|------|-------|\n| next_default_type | improve |\n",
        encoding="utf-8",
    )
    (tmp_path / "PROJECT.md").write_text("# TestProj\n\nContext", encoding="utf-8")

    def mock_failing_call(api_key, user_prompt, language):
        raise RuntimeError("Simulated LLM failure")

    monkeypatch.setenv("MINIMAX_API_KEY", "test-key-fail")
    monkeypatch.setattr("scripts.llm_client._call_minimax", mock_failing_call)

    from scripts.task_planner import choose_next_task, PlannedTask
    from scripts.roadmap import RoadmapState

    roadmap = RoadmapState(
        current_task=None,
        maintenance_mode=False,
        next_default_type="improve",
        improves_since_last_idea=0,
        post_feature_maintenance_remaining=0,
        maintenance_anchor_title="",
        current_plan_path="",
        reserved_user_task_id="",
    )

    planned, consumed = choose_next_task(
        tmp_path, roadmap, done_titles=set(), language="zh",
        forbidden_titles=set(), use_llm=True
    )

    # Should fall back to pool
    assert isinstance(planned, PlannedTask)
    assert planned.title != ""  # got something from pool


def test_choose_next_task_auto_detects_llm_key(monkeypatch, tmp_path):
    """When use_llm=None, choose_next_task auto-detects MINIMAX_API_KEY."""
    (tmp_path / ".ail").mkdir()
    rm = tmp_path / ".ail" / "ROADMAP.md"
    rm.write_text(
        "# Roadmap\n\n## Rhythm State\n\n| field | value |\n|------|-------|\n| next_default_type | improve |\n",
        encoding="utf-8",
    )
    (tmp_path / "PROJECT.md").write_text("# TestProj\n\nContext", encoding="utf-8")

    called = [False]

    def mock_call(api_key, user_prompt, language):
        called[0] = True
        return json.dumps({
            "title": "Auto-detected LLM task",
            "task_type": "improve",
            "background": "",
            "goal": "",
            "context": "Test",
            "scope": [],
            "non_goals": [],
            "relevant_files": [],
            "execution_plan": [],
            "acceptance_criteria": [],
            "why_now": "",
            "risks": "",
            "rollback": "",
        })

    monkeypatch.setenv("MINIMAX_API_KEY", "auto-detect-key")
    monkeypatch.setattr("scripts.llm_client._call_minimax", mock_call)

    from scripts.task_planner import choose_next_task, PlannedTask
    from scripts.roadmap import RoadmapState

    roadmap = RoadmapState(
        current_task=None,
        maintenance_mode=True,
        next_default_type="improve",
        improves_since_last_idea=0,
        post_feature_maintenance_remaining=0,
        maintenance_anchor_title="",
        current_plan_path="",
        reserved_user_task_id="",
    )

    planned, consumed = choose_next_task(
        tmp_path, roadmap, done_titles=set(), language="zh",
        forbidden_titles=set(), use_llm=None  # auto-detect
    )

    assert called[0], "LLM should have been called when MINIMAX_API_KEY is set"
    assert planned.title == "Auto-detected LLM task"
    assert planned.source == "llm"  # LLM path was taken
