# LLM-Powered PM + Maintenance Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add MiniMax LLM integration for AI-powered plan generation + maintenance mode switch

**Architecture:** LLM layer is a new `llm_client.py` module that wraps MiniMax SDK. Maintenance mode is a flag in ROADMAP rhythm state that restricts the candidate pool. Both are orthogonal and share `scripts/task_planner.py` as the integration point.

**Tech Stack:** `minimax` pip package, Python dataclasses, `subprocess` for git context

---

## File Map

```
scripts/
  llm_client.py     [CREATE] MiniMax SDK wrapper, generate_pm_plan()
  llm_prompts.py    [CREATE] SYSTEM_PROMPT + USER_PROMPT_TEMPLATE
  task_planner.py   [MODIFY] add _MAINTENANCE_CANDIDATES, integrate LLM path, maintenance_mode flag
  roadmap.py        [MODIFY] add maintenance_mode to RhythmState dataclass
  cli.py            [MODIFY] add cmd_maintenance(), modify cmd_plan() to use LLM

tests/
  test_llm_client.py      [CREATE] unit tests for llm_client
  test_maintenance_mode.py [CREATE] tests for maintenance mode flag + pool restriction
  test_task_planner.py    [MODIFY] update for new choose_next_task signature/behaviour
```

---

## Task 1: LLM Client Module

**Files:**
- Create: `scripts/llm_client.py`
- Test: `tests/test_llm_client.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_llm_client.py
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
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_llm_client.py -v
```
Expected: FAIL — `scripts.llm_client` does not exist

- [ ] **Step 3: Write minimal implementation**

`scripts/llm_client.py`:

```python
"""LLM client for AI-powered PM plan generation via MiniMax."""
from __future__ import annotations
import json, os, re
from dataclasses import dataclass, field
from pathlib import Path

API_BASE = "https://api.minimaxi.com"
MODEL = "MiniMax-M2.7"

class MiniMaxError(Exception):
    """Raised on API key missing, network error, or non-200 response."""

class JSONParseError(MiniMaxError):
    """Raised when LLM output is not valid JSON."""

@dataclass
class PMPlan:
    title: str
    task_type: str = "improve"
    source: str = "pm"
    effort: str = "medium"
    background: str = ""
    goal: str = ""
    context: str = ""
    scope: list[str] = field(default_factory=list)
    non_goals: list[str] = field(default_factory=list)
    relevant_files: list[str] = field(default_factory=list)
    execution_plan: list[str] = field(default_factory=list)
    acceptance_criteria: list[str] = field(default_factory=list)
    why_now: str = ""
    risks: str = ""
    rollback: str = ""
    maintenance_tag: str = ""

def _get_api_key() -> str:
    key = os.environ.get("MINIMAX_API_KEY", "").strip()
    if not key:
        raise EnvironmentError("MINIMAX_API_KEY environment variable is not set.")
    return key

def _parse_json_response(raw: str) -> PMPlan:
    """Parse LLM JSON output into PMPlan. Strips markdown fences if present."""
    stripped = raw.strip()
    # Remove triple-backtick JSON fences
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    try:
        data = json.loads(stripped)
    except json.JSONDecodeError as e:
        raise JSONParseError(f"LLM output is not valid JSON: {e}\n--- raw:\n{raw[:500]}")
    return PMPlan(
        title=data.get("title", "Untitled"),
        task_type=data.get("task_type", "improve"),
        source=data.get("source", "pm"),
        effort=data.get("effort", "medium"),
        background=data.get("background", ""),
        goal=data.get("goal", ""),
        context=data.get("context", ""),
        scope=data.get("scope", []),
        non_goals=data.get("non_goals", []),
        relevant_files=data.get("relevant_files", []),
        execution_plan=data.get("execution_plan", []),
        acceptance_criteria=data.get("acceptance_criteria", []),
        why_now=data.get("why_now", ""),
        risks=data.get("risks", ""),
        rollback=data.get("rollback", ""),
        maintenance_tag=data.get("maintenance_tag", ""),
    )

def generate_pm_plan(project: Path, language: str = "zh") -> PMPlan:
    """Two-step LLM workflow: context analysis → plan generation.
    
    Step 1: Ask LLM to read project context (ROADMAP, PROJECT.md, recent git).
    Step 2: Ask LLM to generate a structured JSON plan.
    
    Returns PMPlan dataclass.
    Raises MiniMaxError on any failure.
    """
    from scripts.llm_prompts import build_plan_prompt
    api_key = _get_api_key()
    user_prompt = build_plan_prompt(project, language)
    response = _call_minimax(api_key, user_prompt, language)
    return _parse_json_response(response)

def _call_minimax(api_key: str, user_prompt: str, language: str) -> str:
    """Call MiniMax /v1/text/chat/completion API. Returns response content."""
    import urllib.request, urllib.error
    payload = {
        "model": MODEL,
        "messages": [
            {"role": "user", "content": user_prompt}
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}/v1/text/chat/completion",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raise MiniMaxError(f"MiniMax API HTTP {e.code}: {e.reason}")
    except urllib.error.URLError as e:
        raise MiniMaxError(f"Network error: {e.reason}")
    choices = data.get("choices", [])
    if not choices:
        raise MiniMaxError(f"Empty response from MiniMax API: {data}")
    return choices[0].get("text") or choices[0].get("message", {}).get("content", "")
```

`scripts/llm_prompts.py`:

```python
"""Prompts for LLM-powered PM plan generation."""
from pathlib import Path

def build_plan_prompt(project: Path, language: str) -> str:
    """Build the user prompt for PM plan generation.
    
    Step 1 context is built inline by reading key files.
    Step 2 instructs LLM to output JSON.
    """
    roadmap_text = _read_if_exists(project / ".ail" / "ROADMAP.md")
    project_md = _read_if_exists(project / "PROJECT.md")
    recent_commits = _git_recent_commits(project)
    scripts_list = _list_scripts(project)
    
    context = f"""## Project Context

### ROADMAP.md (current state)
{roadmap_text or '(no ROADMAP.md)'}

### PROJECT.md
{project_md or '(no PROJECT.md)'}

### Recent Git Commits
{recent_commits or '(no git history)'}

### scripts/ Directory
{scripts_list}
"""
    return f"""{context}

## Your Task
Analyze the project above and generate ONE PM task plan in JSON format.

The task should be:
- Specific and actionable (not generic "improve code quality")
- Relevant to the project's current state and recent history
- Achievable in one work session

Output ONLY valid JSON (no markdown fences, no commentary), with this schema:
{{
  "title": "Short Chinese title for the task",
  "task_type": "improve",
  "effort": "short|medium|long",
  "background": "Why this task exists",
  "goal": "What completing this task achieves",
  "context": "What you know about the project",
  "scope": ["file1.py", "file2.py"],
  "non_goals": ["What this task does NOT cover"],
  "relevant_files": ["files to look at or modify"],
  "execution_plan": ["Step 1: ...", "Step 2: ..."],
  "acceptance_criteria": ["Criterion 1", "Criterion 2"],
  "why_now": "Why this task should be done now",
  "risks": "Potential risks or concerns",
  "rollback": "How to revert if needed"
}}
"""

def _read_if_exists(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")[:8000]
    except Exception:
        return ""

def _git_recent_commits(project: Path, n: int = 10) -> str:
    import subprocess
    r = subprocess.run(
        ["git", "log", "--oneline", f"-n{n}"],
        cwd=project, capture_output=True, text=True, timeout=10
    )
    return r.stdout.strip() if r.returncode == 0 else ""

def _list_scripts(project: Path) -> str:
    scripts_dir = project / "scripts"
    if not scripts_dir.exists():
        return "(no scripts/ directory)"
    lines = []
    for p in sorted(scripts_dir.glob("*.py")):
        lines.append(f"{p.name} ({p.stat().st_size // 1024}kb)")
    return "\n".join(lines) if lines else "(no .py files)"
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_llm_client.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```
git add scripts/llm_client.py scripts/llm_prompts.py tests/test_llm_client.py
git commit -m "feat(llm): add MiniMax client module and prompt builder"
```

---

## Task 2: Maintenance Mode Candidates + Rhythm State

**Files:**
- Modify: `scripts/roadmap.py`
- Modify: `scripts/task_planner.py`
- Create: `tests/test_maintenance_mode.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_maintenance_mode.py
import pytest
from pathlib import Path
from scripts.roadmap import RoadmapState, CurrentTask

def test_roadmap_has_maintenance_mode_field():
    rs = RoadmapState(
        current_task=None,
        next_default_type="improve",
        improves_since_last_idea=0,
        post_feature_maintenance_remaining=0,
        maintenance_anchor_title="",
        current_plan_path="",
        reserved_user_task_id="",
    )
    assert hasattr(rs, "maintenance_mode")
    assert rs.maintenance_mode == False

def test_maintenance_candidates_exist():
    from scripts.task_planner import _MAINTENANCE_CANDIDATES
    assert len(_MAINTENANCE_CANDIDATES) >= 10
    tags = {c.get("maintenance_tag", "") for c in _MAINTENANCE_CANDIDATES}
    assert "testing" in tags
    assert "docs" in tags
    assert "deps" in tags
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_maintenance_mode.py -v
```
Expected: FAIL — `maintenance_mode` not in RoadmapState

- [ ] **Step 3: Modify RoadmapState**

Add `maintenance_mode: bool = False` field to `RoadmapState` dataclass in `scripts/roadmap.py`:

```python
@dataclass
class RoadmapState:
    current_task: CurrentTask | None
    next_default_type: str = "idea"
    improves_since_last_idea: int = 0
    post_feature_maintenance_remaining: int = 0
    maintenance_anchor_title: str = ""
    current_plan_path: str = ""
    reserved_user_task_id: str = ""
    maintenance_mode: bool = False   # ← NEW
```

Also update `load_roadmap()` to parse `maintenance_mode` from the rhythm state table.

- [ ] **Step 4: Add maintenance candidates to task_planner.py**

Add `_MAINTENANCE_CANDIDATES` list after `_IMPROVE_CANDIDATES`:

```python
_MAINTENANCE_CANDIDATES: list[dict] = [
    {"title": "补充单元测试覆盖，提升关键函数的测试用例数量", "task_type": "maintenance", "maintenance_tag": "testing"},
    {"title": "补充集成测试覆盖，验证模块间交互", "task_type": "maintenance", "maintenance_tag": "testing"},
    {"title": "更新项目依赖版本，检查安全更新", "task_type": "maintenance", "maintenance_tag": "deps"},
    {"title": "进行安全漏洞审计，检查常见安全风险", "task_type": "maintenance", "maintenance_tag": "security"},
    {"title": "提升代码可读性，重命名不清晰的变量和函数", "task_type": "maintenance", "maintenance_tag": "readability"},
    {"title": "完善错误处理，为核心函数添加异常处理", "task_type": "maintenance", "maintenance_tag": "error-handling"},
    {"title": "完善日志语句，提升可调试性", "task_type": "maintenance", "maintenance_tag": "logging"},
    {"title": "进行性能 profiling，识别并优化性能瓶颈", "task_type": "maintenance", "maintenance_tag": "performance"},
    {"title": "更新项目文档，确保 README 和 CHANGELOG 最新", "task_type": "maintenance", "maintenance_tag": "docs"},
    {"title": "清理无用代码和文件，减少技术债务", "task_type": "maintenance", "maintenance_tag": "cleanup"},
    {"title": "修复已知的边界 case，提升鲁棒性", "task_type": "maintenance", "maintenance_tag": "bug"},
    {"title": "提升配置灵活性，减少硬编码", "task_type": "maintenance", "maintenance_tag": "config"},
    {"title": "代码重复检测和消除，提升复用性", "task_type": "maintenance", "maintenance_tag": "refactor"},
    {"title": "完善项目可复现性验证，确保构建步骤可重复", "task_type": "maintenance", "maintenance_tag": "reproducibility"},
    {"title": "补充横向移动工具脚本，提升日常开发效率", "task_type": "maintenance", "maintenance_tag": "tooling"},
]
```

- [ ] **Step 5: Modify choose_next_task to respect maintenance_mode**

In `choose_next_task()`, after loading roadmap, check `roadmap.maintenance_mode`. If True, restrict to `_MAINTENANCE_CANDIDATES` only (ignore `next_default_type` rhythm logic).

```python
# In choose_next_task(), after roadmap = load_roadmap(...)
if getattr(roadmap, "maintenance_mode", False):
    # Override: only maintenance candidates
    primary_pool = [_make_task("maintenance", c, ctx) for c in _MAINTENANCE_CANDIDATES]
    fallback_pool = primary_pool
```

- [ ] **Step 6: Run tests to verify they pass**

```
pytest tests/test_maintenance_mode.py tests/test_task_planner.py -v
```
Expected: PASS

- [ ] **Step 7: Commit**

```
git add scripts/roadmap.py scripts/task_planner.py tests/test_maintenance_mode.py
git commit -m "feat(maintenance): add maintenance_mode flag and candidate pool"
```

---

## Task 3: a-maintenance CLI Command

**Files:**
- Modify: `scripts/cli.py`
- Test: `tests/test_maintenance_mode.py` (add toggle tests)

- [ ] **Step 1: Write failing test**

```python
# tests/test_maintenance_mode.py (add)
def test_maintenance_command_on(tmp_path, capsys):
    # Set up minimal project
    (tmp_path / ".ail").mkdir()
    rm = tmp_path / ".ail" / "ROADMAP.md"
    rm.write_text("# Roadmap\n\n## Rhythm State\n\n| field | value |\n|------|-------|\n| next_default_type | improve |\n| improves_since_last_idea | 0 |\n| maintenance_mode | false |\n", encoding="utf-8")
    result = _run(["a-maintenance", "on"], cwd=tmp_path)
    assert result.returncode == 0
    assert "maintenance mode enabled" in result.stdout.lower()
    content = rm.read_text(encoding="utf-8")
    assert "maintenance_mode | true" in content

def test_maintenance_command_off(tmp_path, capsys):
    # Set up minimal project with maintenance_mode=true
    (tmp_path / ".ail").mkdir()
    rm = tmp_path / ".ail" / "ROADMAP.md"
    rm.write_text("# Roadmap\n\n## Rhythm State\n\n| field | value |\n|------|-------|\n| next_default_type | improve |\n| improves_since_last_idea | 0 |\n| maintenance_mode | true |\n", encoding="utf-8")
    result = _run(["a-maintenance", "off"], cwd=tmp_path)
    assert result.returncode == 0
    content = rm.read_text(encoding="utf-8")
    assert "maintenance_mode | false" in content

def test_maintenance_command_status(tmp_path, capsys):
    (tmp_path / ".ail").mkdir()
    rm = tmp_path / ".ail" / "ROADMAP.md"
    rm.write_text("# Roadmap\n\n## Rhythm State\n\n| field | value |\n|------|-------|\n| maintenance_mode | true |\n", encoding="utf-8")
    result = _run(["a-maintenance", "status"], cwd=tmp_path)
    assert result.returncode == 0
    assert "enabled" in result.stdout.lower()
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_maintenance_mode.py::test_maintenance_command_on -v
```
Expected: FAIL — `a-maintenance` command does not exist

- [ ] **Step 3: Implement cmd_maintenance()**

In `scripts/cli.py`:

```python
def cmd_maintenance(action: str) -> None:
    """Enable, disable, or check maintenance mode.
    
    Args:
        action: "on", "off", or "status"
    """
    from scripts.roadmap import load_roadmap, set_current_task, CurrentTask
    project, roadmap_path = _get_roadmap_and_project()
    _migrate_to_ail(project)
    if not roadmap_path.exists():
        fail("No ROADMAP.md found. Run 'a-plan' first.")
        sys.exit(1)
    roadmap = load_roadmap(roadmap_path)
    
    if action == "status":
        mode = getattr(roadmap, "maintenance_mode", False)
        status = c("enabled", COLOR_GREEN) if mode else c("disabled", COLOR_YELLOW)
        print(f"  Maintenance mode: {status}")
        return
    
    if action not in ("on", "off"):
        fail("Usage: a-maintenance on|off|status")
        sys.exit(1)
    
    new_mode = action == "on"
    step(f"{c('Maintenance Mode', COLOR_BOLD)}: {'enable' if new_mode else 'disable'}")
    
    current = roadmap.current_task
    plan_path = roadmap.current_plan_path
    set_current_task(
        roadmap_path,
        current,
        plan_path=plan_path,
        next_default_type=roadmap.next_default_type,
        improves_since_last_idea=roadmap.improves_since_last_idea,
        post_feature_maintenance_remaining=roadmap.post_feature_maintenance_remaining,
        maintenance_anchor_title=roadmap.maintenance_anchor_title,
        reserved_user_task_id=roadmap.reserved_user_task_id,
        maintenance_mode=new_mode,
    )
    ok(f"Maintenance mode {'enabled' if new_mode else 'disabled'}")
```

- [ ] **Step 4: Register in init.py argument parser**

In `scripts/init.py` `main()` function, add subparser:

```python
maint_p = sub.add_parser("a-maintenance", help="Manage maintenance mode")
maint_p.add_argument("action", choices=["on", "off", "status"], nargs="?", default="status")
maint_p.set_defaults(func=lambda args: cmd_maintenance(args.action))
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_maintenance_mode.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```
git add scripts/cli.py scripts/init.py tests/test_maintenance_mode.py
git commit -m "feat(cli): add a-maintenance on/off/status command"
```

---

## Task 4: Integrate LLM into a-plan

**Files:**
- Modify: `scripts/cli.py` (`cmd_plan`)
- Modify: `scripts/task_planner.py` (LLM path)
- Test: Update `tests/test_task_planner.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_llm_client.py (add integration test)
def test_generate_pm_plan_with_mock(monkeypatch, tmp_path):
    # Create a fake project
    (tmp_path / ".ail").mkdir()
    rm = tmp_path / ".ail" / "ROADMAP.md"
    rm.write_text("# Roadmap\n\n## Rhythm State\n\n| field | value |\n|------|-------|\n| next_default_type | improve |\n", encoding="utf-8")
    (tmp_path / "PROJECT.md").write_text("# TestProj\n\nContext", encoding="utf-8")
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")
    # Mock HTTP response
    class FakeResponse:
        def __init__(self, data): self._data = json.dumps(data).encode()
        def read(self): return self._data
        def __enter__(self): return self
        def __exit__(self, *a): pass
    class FakeHTTPError(Exception): pass
    import urllib.error
    def fake_open(req, timeout=None):
        body = json.loads(req.data)
        if "test-key" not in str(req.headers.get("Authorization", "")):
            raise FakeHTTPError("Unauthorized")
        return FakeResponse({
            "choices": [{"text": json.dumps({
                "title": "Improve test coverage",
                "task_type": "improve",
                "background": "Tests are minimal",
                "goal": "Add more tests",
                "context": "Test project",
                "scope": ["tests/"],
                "non_goals": [],
                "relevant_files": ["tests/test_a.py"],
                "execution_plan": ["Step 1: write tests"],
                "acceptance_criteria": ["Coverage > 80%"],
                "why_now": "Quality",
                "risks": "None",
                "rollback": "git revert",
            })}]
        })
    monkeypatch.setattr("urllib.request.urlopen", fake_open)
    plan = generate_pm_plan(tmp_path, "zh")
    assert plan.title == "Improve test coverage"
    assert plan.task_type == "improve"
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_llm_client.py::test_generate_pm_plan_with_mock -v
```
Expected: FAIL — not implemented yet

- [ ] **Step 3: Modify choose_next_task to use LLM**

In `scripts/task_planner.py`, modify `choose_next_task()` signature to accept optional `use_llm=False`. When `MINIMAX_API_KEY` is set in environment, auto-enable LLM path:

```python
def choose_next_task(
    project: Path,
    roadmap,
    done_titles: set[str],
    language: str = "zh",
    forbidden_titles: set[str] | None = None,
    use_llm: bool | None = None,   # NEW: None = auto-detect
) -> tuple[PlannedTask, bool]:
```

Internal logic:

```python
# At start of choose_next_task:
if use_llm is None:
    use_llm = bool(os.environ.get("MINIMAX_API_KEY", "").strip())

if use_llm:
    from scripts.llm_client import generate_pm_plan as llm_generate
    api_key = os.environ.get("MINIMAX_API_KEY", "").strip()
    if not api_key:
        raise MiniMaxError("MINIMAX_API_KEY not set")
    raw_plan = llm_generate(project, language)
    return _plan_to_planned_task(raw_plan), False

# Fallback: hard-coded pool (existing logic unchanged)
```

Add `_plan_to_planned_task()` helper to convert `PMPlan` dataclass → `PlannedTask`:

```python
def _plan_to_planned_task(plan: PMPlan) -> PlannedTask:
    return PlannedTask(
        title=plan.title,
        task_type=plan.task_type,
        source=plan.source,
        effort=plan.effort,
        context=plan.context,
        why_now=plan.why_now,
        scope="\n".join(plan.scope),
        non_goals="\n".join(plan.non_goals),
        relevant_files="\n".join(plan.relevant_files),
        execution_plan="\n".join(plan.execution_plan),
        acceptance_criteria="\n".join(plan.acceptance_criteria),
        verification=f"cd {project} && python3 -m pytest tests/ -q",
        risks=plan.risks,
        background=plan.background,
        rollback=plan.rollback,
    )
```

- [ ] **Step 4: Update cmd_plan to pass use_llm flag**

In `scripts/cli.py` `cmd_plan()`, detect LLM availability:

```python
use_llm = bool(os.environ.get("MINIMAX_API_KEY", "").strip())
planned, consumed = choose_next_task(
    project, roadmap, done_titles, language,
    forbidden_titles=forbidden_titles,
    use_llm=use_llm,   # NEW
)
```

- [ ] **Step 5: Run tests**

```
pytest tests/test_llm_client.py tests/test_task_planner.py -v
```
Expected: PASS

- [ ] **Step 6: Commit**

```
git add scripts/task_planner.py scripts/cli.py tests/test_llm_client.py
git commit -m "feat(llm): integrate LLM plan generation into choose_next_task"
```

---

## Task 5: Final Integration + Full Test

- [ ] **Step 1: Run full test suite**

```
python3 -m pytest tests/ -q
```
Expected: 70+ passed (69 existing + new tests from Task 1 & 2)

- [ ] **Step 2: Manual smoke test**

```bash
# Test a-maintenance on skill itself
cd /Users/weiminglu/Projects/autonomous-improvement-loop
python3 scripts/init.py a-maintenance status
# Expected: maintenance mode disabled

python3 scripts/init.py a-maintenance on
# Expected: maintenance mode enabled

python3 scripts/init.py a-maintenance off
# Expected: maintenance mode disabled
```

- [ ] **Step 3: Bump version and publish**

```bash
python3 scripts/bump_version.py --path . --release
# Version: 8.14.0
git tag -l "v8.14*"
clawhub publish . --version 8.14.0
sleep 30
clawhub update autonomous-improvement-loop --workdir ~/.openclaw/workspace-mia --version 8.14.0 --force
```

- [ ] **Step 4: Commit**

```
git add -A && git commit -m "feat: LLM-powered PM + maintenance mode (8.14.0)"
```

---

## Spec Coverage Check

- [x] LLM Layer: `llm_client.py` + `llm_prompts.py` ✅
- [x] Two-step workflow (context → plan) ✅
- [x] JSON structured output → PMPlan dataclass ✅
- [x] `MINIMAX_API_KEY` env var ✅
- [x] Enhanced mode / fallback = B (LLM-only, no fallback) ✅
- [x] Maintenance Mode flag in rhythm state ✅
- [x] `a-maintenance on/off/status` command ✅
- [x] Maintenance candidate pool (~15 tasks) ✅
- [x] Maintenance mode overrides rhythm logic ✅
- [x] Tests ✅
- [x] Cleanup notes in spec ✅
