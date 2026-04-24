import pytest, json
from pathlib import Path
from scripts.llm_client import PMPlan, generate_pm_plan, MiniMaxError

def test_pmplan_dataclass():
    plan = PMPlan(
        title="Test task",
        task_type="improve",
        background="background",
        goal="goal",
        context="context",
        scope=["tests/"],
        non_goals=["scope"],
        relevant_files=["tests/test_a.py"],
        execution_plan=["Step 1"],
        acceptance_criteria=["criterion"],
        why_now="why",
    )
    assert plan.title == "Test task"
    assert plan.maintenance_tag == ""

def test_generate_pm_plan_requires_api_key(monkeypatch):
    monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
    with pytest.raises(EnvironmentError, match="MINIMAX_API_KEY"):
        generate_pm_plan(Path("/tmp"))

def test_parse_valid_json_response():
    raw = json.dumps({
        "title": "Improve error handling",
        "task_type": "improve",
        "background": "Many functions lack try/except",
        "goal": "Add error handling to core functions",
        "context": "Project has 5 modules",
        "scope": ["scripts/cli.py", "scripts/state.py"],
        "non_goals": ["Do not rewrite existing logic"],
        "relevant_files": ["scripts/cli.py"],
        "execution_plan": ["Step 1: audit existing try blocks", "Step 2: add handlers"],
        "acceptance_criteria": ["All core functions have error handlers"],
        "why_now": "Production errors are hard to debug",
        "risks": "May break existing error masking",
        "rollback": "git revert scripts/cli.py",
    })
    from scripts.llm_client import _parse_json_response
    plan = _parse_json_response(raw)
    assert plan.title == "Improve error handling"
    assert plan.task_type == "improve"
    assert "scripts/cli.py" in plan.scope

def test_parse_invalid_json_raises_runtime_error():
    from scripts.llm_client import _parse_json_response
    with pytest.raises(RuntimeError, match="JSON"):
        _parse_json_response("not json at all")
