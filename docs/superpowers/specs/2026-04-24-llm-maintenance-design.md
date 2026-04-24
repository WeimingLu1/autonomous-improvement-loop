# LLM-Powered PM + Maintenance Mode — Design Spec

## Overview

Two independent features bundled in one release:

1. **LLM Layer** (`scripts/llm_client.py`) — MiniMax SDK integration for AI-powered plan generation
2. **Maintenance Mode** — `a-maintenance` command + rhythm-state flag to restrict PM to maintenance tasks only

---

## Feature 1: LLM Layer

### Module

`scripts/llm_client.py`

### Responsibilities

- Encapsulate all MiniMax API calls
- Provide structured JSON plan generation from project context
- Parse LLM JSON output into typed Python dataclasses

### Dependencies

```bash
pip install minimax  # Official MiniMax Python SDK
```

API base: `https://api.minimaxi.com`

### API Key

Read from environment variable `MINIMAX_API_KEY`. Raise `EnvironmentError` if not set.

### Core Function

```python
def generate_pm_plan(
    project: Path,
    language: str = "zh",
) -> PMPlan:
    """
    Two-step LLM workflow:
    1. Context analysis — read ROADMAP.md, PROJECT.md, recent git diff
    2. Plan generation — output structured JSON

    Returns PMPlan dataclass (see below).
    Raises RuntimeError on API failure.
    """
```

### PMPlan Dataclass

```python
@dataclass
class PMPlan:
    title: str
    task_type: str          # "improve" | "idea" | "maintenance" | "bug" | "testing"
    source: str = "pm"
    effort: str = "medium"  # "short" | "medium" | "long"
    background: str
    goal: str
    context: str
    scope: list[str]
    non_goals: list[str]
    relevant_files: list[str]
    execution_plan: list[str]
    acceptance_criteria: list[str]
    why_now: str
    risks: str
    rollback: str = ""
    maintenance_tag: str = ""  # e.g. "testing", "docs", "deps" — set when maintenance_mode=True
```

### System Prompt

`scripts/llm_prompts.py` — contains `SYSTEM_PROMPT` and `USER_PROMPT_TEMPLATE`.

**Step 1 prompt** (context analysis): Extract project state, recent commits, open issues.

**Step 2 prompt** (plan generation): Given Step 1 output, generate a structured JSON plan matching `PMPlan` schema.

LLM response **must** be valid JSON (no markdown fences, no commentary).

### Error Handling

- `MINIMAX_API_KEY` not set → `EnvironmentError`
- API error / timeout → `RuntimeError`
- LLM output invalid JSON → `RuntimeError` with partial output for debugging
- Non-200 HTTP status → `RuntimeError`

### Integration Points

- `scripts/task_planner.py`: `choose_next_task()` calls `llm_client.generate_pm_plan()` instead of hard-coded pool when `MINIMAX_API_KEY` is set
- Fallback: **none** — if `MINIMAX_API_KEY` is set, LLM is required; if not set, feature is unavailable

---

## Feature 2: Maintenance Mode

### Command

`a-maintenance on | off | status`

- `on`: Set `maintenance_mode = true` in ROADMAP.md rhythm state
- `off`: Set `maintenance_mode = false`
- `status`: Print current mode

### ROADMAP.md Rhythm State Schema Change

```diff
| field | value |
|------|-------|
| next_default_type | improve |
| improves_since_last_idea | 0 |
| maintenance_mode | false |   ← NEW
| reserved_user_task_id |  |
```

### Maintenance Candidate Pool

In `scripts/task_planner.py`, add `_MAINTENANCE_CANDIDATES` (~15 tasks):

1. 补充单元测试覆盖
2. 补充集成测试覆盖
3. 更新项目依赖版本
4. 安全漏洞审计
5. 代码可读性提升（重命名、注释）
6. 错误处理完善
7. 日志语句完善
8. 性能 profiling 和优化
9. 文档更新（README、CHANGELOG）
10. 清理无用代码和文件
11. 修复已知边界 case
12. 提升配置灵活性
13. 代码重复检测和消除
14. 横向移动工具脚本完善
15. 项目可复现性验证（setup、构建步骤）

### Rhythm Behavior

- `maintenance_mode = true`: `choose_next_task()` restricts to `_MAINTENANCE_CANDIDATES`, ignores rhythm counters
- `maintenance_mode = false`: Normal PM cycle resumes (idea → improve → auto-maintenance after feature)

### Self-Hosting Override

When skill runs on itself, `maintenance_mode` is always `false` (skill doesn't maintenance itself).

---

## CLI Commands

| Command | File | Description |
|---------|------|-------------|
| `a-maintenance` | `scripts/cli.py` | on/off/status for maintenance mode |
| `a-plan` | `scripts/cli.py` | Now uses `llm_client.generate_pm_plan()` if API key present |
| `a-trigger` | `scripts/cli.py` | Unchanged |
| `a-add` | `scripts/cli.py` | Unchanged |

---

## Config Changes

`config.md` (project-level `.ail/config.md`):

```diff
+ llm_enabled: true          # set automatically when MINIMAX_API_KEY detected
+ maintenance_mode: false   # user-controlled via a-maintenance
```

---

## Cleanup

- Remove hard-coded candidate pools from `task_planner.py` that are superseded by LLM generation
- Keep `_STICKY_DONE_TITLES`, `_bootstrap_title`, and rhythm-related helpers
- Keep `choose_next_task()` signature unchanged; internally switch between LLM and pool

---

## Testing

1. `test_llm_client.py`: Mock `minimax` SDK responses; test JSON parsing, error handling
2. `test_maintenance_mode.py`: Test flag toggle, candidate pool restriction, rhythm behavior
3. `test_integration_llm.py`: End-to-end test with real API (requires `MINIMAX_API_KEY`)
4. All existing tests pass without modification

---

## Version

Target: `8.14.0` (major.minor.patch bump to `8.14.0` to reflect new capability)

---

## Risks / Notes

- LLM output format may drift; add schema validation in `generate_pm_plan()`
- Rate limiting: MiniMax has rate limits; add retry with exponential backoff
- Maintenance Mode candidates are hard-coded (not LLM-generated); this is intentional for stability
