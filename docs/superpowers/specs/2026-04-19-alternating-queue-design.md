# Alternating Queue — Design Specification

> **Status:** Approved 2026-04-19
> **Skill:** autonomous-improvement-loop
> **Design phase:** brainstorming complete

---

## 1. Overview

The autonomous-improvement-loop skill manages a queue of tasks in HEARTBEAT.md.
Previously, all queue items came from `[[Improve]]` tag scanning — maintenance
tasks with no functional direction. This design introduces a second task type,
`[[Idea]]`, and enforces strict alternation between them.

**Goals:**
- Queue always contains exactly one task type at a time (alternation enforced by system, not agent)
- `[[Idea]]` items propose genuinely innovative, actionable features
- `[[Improve]]` items are targeted improvements derived from recent project activity
- The alternation rhythm is **2 Improve → 1 Idea** (fixed, not dynamic)

---

## 2. Alternation Mechanism

### 2.1 Core Rule

Every `inspire_scanner` run decides what to generate based on Done Log:

```
Read last Done Log entry:
  ├── type = [[Idea]]  → generate [[Improve]]
  ├── type = [[Improve]] → check improves_since_last_idea counter
  │                      ├── counter < 2  → generate [[Improve]] (counter + 1)
  │                      └── counter >= 2 → generate [[Idea]]  (counter → 0)
  └── no entries (first run) → generate [[Idea]]
```

### 2.2 State: `improves_since_last_idea`

- Stored in HEARTBEAT `## Run Status` table as `improves_since_last_idea : N`
- Written by `inspire_scanner` after every run
- Read by `inspire_scanner` at the start of each run to decide what to generate
- Reset to `0` whenever an Idea is generated

### 2.3 Queue Invariant

- On every `inspire_scanner` run, the **entire same-type queue block is replaced** with the new single item
- Old `[[Idea]]` items are cleared when a new `[[Idea]]` is generated
- Old `[[Improve]]` items are cleared when a new `[[Improve]]` is generated
- Result: queue always has exactly 1 item — no choice for the agent

### 2.4 Cron Message Guidance

`init.py` cron message updated to:

> Execute the current pending queue item. The item type alternates: after a `[[Improve]]`, expect a `[[Idea]]` next (and vice versa). No need to choose — there is only ever one pending item.

---

## 3. Idea Generation

### 3.1 When

Generated on the Idea cycle (every 2 Improve cycles). Exactly **1 Idea per Idea cycle**.

### 3.2 Content

Each Idea is a single, concrete, actionable functional improvement sourced from
PROJECT.md inspire questions. An Idea must satisfy all three:

1. Addresses a real user pain point or workflow gap
2. Capability does not currently exist in the project
3. After implementation, the project value is meaningfully increased

### 3.3 Per-Project-Kind Generators

`inspire_scanner` calls `detect_project_type(project)` then dispatches to the
appropriate generator. Each generator produces 1-3 candidate Ideas, from which
the top-scoring one is selected (or the most specific one if scores tie).

**Software project generators:**

| Trigger | Idea | Score |
|---------|------|-------|
| cli | 添加交互式 `health interactive` 命令，通过问答引导记录健康事件，降低输入门槛 | 65 |
| advisor | 为 `health advisor` 添加方案执行追踪面板，显示每条建议的执行状态 | 65 |
| summary | 添加 `health summary digest --days 7`，自动汇总本周关键变化和异常信号 | 65 |
| log | 为 `health log` 添加 `--dry-run` 选项，先预览解析结果再决定是否写入 | 65 |
| remind | 添加 `health remind snooze <id> --hours 2` 延迟提醒命令 | 65 |
| export | `health export summary` 支持输出 PDF 格式（通过 reportlab 或 weasyprint） | 65 |
| chart | `health summary chart` 支持彩色输出（检测终端支持情况，自动降级） | 65 |
| profile | 支持 `health profile switch <id>` 切换默认 profile，无需每次 --profile-id | 65 |
| rules | 添加饮食热量估算规则：根据 meal 事件中的食物关键词估算摄入热量 | 65 |
| db | 添加 `health db backup --path <path>` 备份数据库到指定位置 | 65 |

Only generators whose trigger module actually exists in the project are activated.

**Writing project generators:**
- 基于问题「作品结构有哪些可以优化的地方？」建议章节重组或深化方案
- 基于问题「有哪些读者反馈还没被转化为具体改进？」建议增加互动或续写方向

**Video project generators:**
- 基于问题「视频内容有哪些薄弱环节观众可能不喜欢？」建议补拍或重新剪辑
- 基于问题「制作流程中有哪些可以自动化或提速的步骤？」建议工具或模板改进

**Research project generators:**
- 基于问题「研究假设有没有被新文献推翻的风险？」建议更新文献综述
- 基于问题「论文中有哪些论证链条还不够严谨？」建议加强论据

**Generic project generators (fallback):**
- 审视项目，找出用户抱怨最多或最影响工作效率的一个具体问题，优先修复
- 审视项目结构和用户旅程，找出使用路径中最大的断点，添加对应功能

### 3.4 Idea Score

Default `score = 65` for all Ideas (higher than Improve's 45-60).

---

## 4. Improve Generation

### 4.1 When

Generated on every Improve cycle (alternation counter < 2). Exactly **1 Improve per Improve cycle**.

### 4.2 Content

Improve is derived from **recent Git commit activity** — not generic templates.
The scanner identifies the most-active module in recent commits and generates a
targeted improvement task for that specific module.

**Algorithm for Software projects:**

```
1. Run: git log --oneline -20 --stat
2. Parse stat output, count lines changed per .py file
3. Identify module with most activity (e.g. src/services/reminder_service.py)
4. Based on module type, generate concrete Improve:

   services/    → "基于最近 commit 分析，src/services/{module} 是高频改动模块。"
                    "建议：补充该模块所有公开函数的边界测试（None/空列表/异常输入），"
                    "并验证 recent {module} 公开 API 的合约是否完整"

   cli/         → "cli/{module} 最近改动较多，建议审查并补充错误处理和边界测试，"
                    "确保 --help 和 --json 两种输出模式均有测试覆盖"

   rules/       → "rules/{module} 规则引擎最近有改动，建议补充该规则的"
                    "全部边界情况测试（窗口边界、None 字段、极端值）"

   parsers/     → "parsers/{module} 最近有更新，建议补充解析器的"
                    "边界测试（空输入、畸形输入、特殊字符、超长输入）"

   other        → "最近高频改动的 {module} 建议进行全面审查，"
                    "补充单元测试和 docstring"
```

### 4.3 Improve Score

Default `score = 45` (lower than Idea's 65). Queue is sorted descending by
score, so Ideas naturally appear first if both types co-exist temporarily.

---

## 5. Generics: Plugin Architecture

### 5.1 Project Kind Detection

`detect_project_type(project: Path) -> Literal["software", "writing", "video", "research", "generic"]`

Used at the top of `inspire_scanner.run_inspire_scan()` to select the correct
generator set.

### 5.2 Per-Kind Dispatch Table

```python
IDEA_GENERATORS: dict[str, list[IdeaGenerator]] = {
    "software":  software_idea_generators,   # trigger → list of IdeaCandidates
    "writing":   writing_idea_generators,
    "video":     video_idea_generators,
    "research":  research_idea_generators,
    "generic":   generic_idea_generators,
}

IMPROVE_GENERATORS: dict[str, ImproveGenerator] = {
    "software":  software_improve_generator,
    "writing":   writing_improve_generator,
    "video":     video_improve_generator,
    "research":  research_improve_generator,
    "generic":   generic_improve_generator,
}
```

Each generator is a plain function: `(project: Path, language: str, seen: set[str]) -> list[Candidate]`

---

## 6. Queue Format

All queue items use the 8-column table format (compatible with existing parsers):

```
| # | Type | Score | Content | Detail | Source | Status | Created |
|---|------|-------|---------|--------|--------|--------|--------|
| 1 | idea | 65 | [[Idea]] 添加交互式 `health interactive` 命令... | 添加交互式... | inspire: CLI 工具有哪些交互范式可以创新？ | pending | 2026-04-19 |
```

- `type`: `idea` or `improve`
- `Score`: 65 for ideas, 45 for improves
- `Content`: Full task description with tag
- `Detail`: Same as Content for compatibility
- `Source`: Either `inspire: {question}` for ideas, or `git: {module_name}` for improves
- `Status`: always `pending` when written
- `Created`: ISO date of generation

Old queue items of the same type are always replaced. Queue is never allowed
to accumulate more than 1 item total.

---

## 7. Run Status Fields

New field added to `## Run Status`:

```
| improves_since_last_idea | 0 |
```

Updated after every `inspire_scanner` run.

Existing fields preserved: `last_run_time`, `last_run_commit`, `last_run_result`,
`last_run_task`, `cron_lock`, `mode`, `rollback_on_fail`.

---

## 8. inspire_scanner API

```python
def run_inspire_scan(
    project: Path,
    heartbeat: Path | None = None,
    *,
    language: str = "zh",
) -> dict:
    """
    Decide what to generate (Idea or Improve) based on alternation state,
    generate content, write to HEARTBEAT queue, update Run Status.

    Returns: {
        "generated": "idea" | "improve",
        "content": "...",       # the generated task text
        "score": int,
        "detail": "...",
        "source": "...",
        "improves_since_last_idea": int,  # state after this run
    }
    """
```

The `every_n` parameter is removed (replaced by alternation counter).

---

## 9. Changes to Existing Components

### 9.1 `update_heartbeat.py`

Step 5 becomes:
```python
# ── 5. Alternating queue: generate next task ───────────────────────────
from inspire_scanner import run_inspire_scan
result = run_inspire_scan(project=project, heartbeat=heartbeat_p, language=language)
print(f"Queue: {result['generated']} — {result['content'][:60]}")
```

Step 6 (PROJECT.md rebuild) unchanged.

### 9.2 `init.py` cron message

Section 4 updated:
> Execute the current pending queue item. Item type alternates: after a `[[Improve]]`, expect a `[[Idea]]` next. No need to choose — there is only ever one pending item.

### 9.3 `inspire_scanner.py`

Complete rewrite:
- Remove `every_n` parameter
- Add `_get_last_done_type()` — reads Done Log, returns `"idea"`, `"improve"`, or `None`
- Add `_get_improves_since_idea(heartbeat)` — reads Run Status
- Add `_set_improves_since_idea(heartbeat, count)` — writes Run Status
- Add `_generate_improve_for_software(project, language, seen)` — Git commit analysis
- Add `_generate_improve_for_{kind}` for writing/video/research/generic
- Restructure `_generate_ideas_for_{kind}` to return list of `(text, question, score)` candidates
- Add `_pick_best_candidate(candidates, seen)` — deduplicate, pick top by score
- Rewrite `run_inspire_scan()` — alternation logic + dispatch
- Delete `_set_inspire_cycle`, `_get_inspire_cycle`, `_pending_idea_count` (old cycle logic)

### 9.4 HEARTBEAT.md

- No structural changes to Queue format (compatible)
- Run Status gets one new row: `| improves_since_last_idea | N |`
- Old `inspire_scan_cycle` field (if present) is cleaned up

---

## 10. Testing Strategy

### 10.1 Unit Tests

`tests/test_inspire_scanner.py`:

| Test | Description |
|------|-------------|
| `test_alternation_first_run_generates_idea` | No Done Log → generates idea |
| `test_alternation_idea_then_improve` | Last was idea → generates improve |
| `test_alternation_improve_then_improve` | Last was improve, counter=1 → generates improve, counter=2 |
| `test_alternation_improve_then_idea` | Last was improve, counter=2 → generates idea, counter=0 |
| `test_improve_resets_counter` | Idea generated → counter resets to 0 |
| `test_duplicate_idea_not_reinserted` | Same idea text already in queue → skipped |
| `test_improve_git_analysis_runs` | Software project → git log is called |
| `test_software_improve_targets_active_module` | With mock git log →Improve targets most-active module |
| `test_writing_improve_targets_stale_chapter` | Writing project → Improve targets oldest chapter |
| `test_queue_replaced_not_appended` | New improve replaces old improve items in queue |
| `test_run_status_updated` | After run → improves_since_last_idea field updated |
| `test_old_inspire_scan_cycle_cleaned` | Old cycle comment/field → removed on first run |

### 10.2 Integration Test

Full `update_heartbeat.py` run (or simulation) with mock git log and real
HEARTBEAT writes — verify final HEARTBEAT queue has exactly 1 item with correct type.

---

## 11. Backward Compatibility

- Existing `[[Improve]]` items in HEARTBEAT are compatible (same table format)
- `update_heartbeat.py` step 5 output changes (shows "Queue: idea — ...") but step numbering stays the same
- `init.py a-queue` command works unchanged (reads same table format)
- `inspire_scanner` CLI interface: `--every-n` parameter removed (breaking change for direct CLI users; update docs)

---

## 12. Open Questions — Resolved

| # | Question | Resolution |
|---|----------|------------|
| 1 | Strict enforcement (A) vs soft guidance (B)? | Strict enforcement (A): only one item type written at a time |
| 2 | Idea quality bar | Actionable innovation: better UX, new capability, workflow improvement |
| 3 | Alternation trigger | Done Log inference (last entry type) |
| 4 | Improve quality | Both Idea and Improve come from inspire_scanner; Improve from Git activity |
| 5 | Improve basis | Recent Git commits — most-active module gets targeted Improve |
| 6 | Idea frequency | 2 Improve → 1 Idea fixed rhythm |
| 7 | Genericity | Option 1: unified dispatch by project kind, built-in generators per kind |
