# Autonomous Improvement Loop — 质量整体升级计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Goal:** 将 AIL 的任务规划质量提升到真正 AI PM 级别——PROJECT.md 详尽准确，任务 plan 内容丰富有深度，不再同质化，cron 链路持续自我完善。

---

## 背景与根因

### 问题 1: PROJECT.md 内容太薄
**根因**: `project_md.py` 的 `detect_tech_stack()` 用字符串包含检测，把注释里的 `sqlalchemy`/`sqlite` 当成了真实依赖。CLI 命令数检测也是错的。核心能力部分不反映真实情况。

**修复方向**: 重写 tech stack 检测（解析 `import` / `from ... import` 语句），加入"最近变更统计"（commits/files）和"核心模块说明"，让 PROJECT.md 真正成为项目理解的第一手资料。

### 问题 2: 任务 Plan 同质化严重
**根因**: `task_planner.py` 只有 3+3 条静态候选，所有 plan 的 context/why_now/scope 完全一样——只有 title 不同。真正的 AI PM plan 应该包含：背景分析、实现细节、分步骤指令、回滚预案、验收指标。

**修复方向**: 大幅扩展 `task_planner.py` 的候选池（目标 20+ 条，每条有差异化的 scope/context），同时让 plan 内容读入真实项目上下文（代码结构、最近 commit），而不只是 `_project_summary` 截取前 400 字。

### 问题 3: 其他问题
- `detect_tech_stack` 误判 → 基于 import 分析重写
- CLI 命令数检测用 `@app.command(` 但 typer 的 decorator 是 `@app.command()`，可能匹配不上
- PROJECT.md 不随 cron 更新
- cron message 里 Mia 生成的 plan 没有被实际执行，只是验证了已存在的内容

---

## 文件结构

需要修改的文件：

- `scripts/task_planner.py` — 重写，AI PM 级任务生成
- `scripts/plan_writer.py` — 增强，加入更多 section
- `scripts/project_md.py` — 修复 tech stack 检测，加入 auto-update 逻辑
- `scripts/init.py` — 加入 PROJECT.md 更新步骤到 cron 工作流
- `scripts/roadmap.py` — 确认 state 结构完整
- `tests/test_task_planner.py` — 新建，覆盖 task_planner 候选去重和内容质量

---

## Task 1: 重建 task_planner.py — AI PM 级任务生成

### 关键文件
- 重写: `scripts/task_planner.py`
- 参考: `docs/superpowers/skills/writing-plans/SKILL.md` 中的 plan 格式

**设计目标**:
- 每次生成 plan 时，读取真实项目上下文：
  - `scripts/` 目录下所有文件的名字和行数
  - 最近 5 条 git commit 的 message 和 diff 摘要
  - `tests/` 目录下已有测试的覆盖情况
- 任务候选池扩展到 **15+ improve + 10+ idea**，每条有差异化 context 和 scope
- context 字段：根据真实文件内容动态生成，不是静态字符串
- scope 字段：具体到文件名和函数名，不是泛泛的"覆盖 a-plan"

**候选池结构**（示例）:

```
improve 候选（15+ 条）:
- "为 init.py 的 a-trigger 命令增加 Dry-run 模式，输出将要执行的操作但不实际执行"
- "为 task_planner.py 增加基于最近 git diff 的自适应候选生成，让任务反映最新代码变化"
- "为 CLI 增加 --json 输出格式，便于脚本解析"
- "为 roadmap.py 的 load_roadmap 增加 schema 验证，对损坏的 ROADMAP.md 给出友好错误"
- ...
```

```
idea 候选（10+ 条）:
- "审视 scripts/ 目录结构，将 >2000 行的 init.py 拆分为多个模块（cli/, state/, cron/）"
- "为项目增加性能基准测试，跟踪 a-plan / a-current 等命令的响应时间"
- ...
```

**每个 PlannedTask 字段**:
- `task_type`, `source`, `title` — 保留
- `context`: 动态读取项目文件内容片断（不是泛泛的 "Project: autonomous-improvement-loop"）
- `why_now`: 结合当前 git 状态和最近 commit，有具体动机
- `scope`: 具体到文件名和函数名，例如 "scripts/init.py:cmd_trigger", "scripts/roadmap.py:load_roadmap"
- `non_goals`: 明确不做什么
- `relevant_files`: 真实的文件路径列表
- `execution_plan`: 列出具体步骤，例如 "Step 1: 在 scripts/init.py 的 cmd_trigger 函数添加 dry_run 参数"
- `acceptance_criteria`: 可量化，例如 "a-trigger --dry-run 输出计划但不写 Done Log"
- `verification`: 实际运行的命令
- `risks`: 已知风险
- **新增**: `background`: 解释为什么这个任务重要（比 why_now 更长）
- **新增**: `rollback`: 如果出错怎么回退
- **新增**: `effort`: estimated time (short/medium/long)

### Steps

- [ ] **Step 1: 备份现有 task_planner.py**

```bash
cp /Users/weiminglu/Projects/autonomous-improvement-loop/scripts/task_planner.py \
   /Users/weiminglu/Projects/autonomous-improvement-loop/scripts/task_planner.py.bak
```

- [ ] **Step 2: 重写 task_planner.py**

重写 `choose_next_task()` 函数，实现：
1. `_read_project_context()` — 读取 scripts/ 下所有 .py 文件名+行数、README.md、最近 git commit
2. `_build_candidates()` — 返回 20+ 条候选，每条有差异化 title/context/scope
3. 从候选池中选取未被 done_titles 去重的任务

- [ ] **Step 3: 测试候选去重**

```bash
cd /Users/weiminglu/Projects/autonomous-improvement-loop
python3 -c "
from scripts.task_planner import choose_next_task
from scripts.roadmap import load_roadmap
from pathlib import Path
roadmap = load_roadmap(Path('.ail/ROADMAP.md'))
done = {'为 a-current 增加完整计划文档回显能力', '为 roadmap 命令流补齐集成测试覆盖'}
for i in range(5):
    t = choose_next_task(Path('.'), roadmap, done, 'zh')
    print(f'{i+1}. [{t.task_type}] {t.title}')
    print(f'   scope: {t.scope}')
    print()
"
```

预期：每次生成不同 title，scope 不重复

- [ ] **Step 4: 运行完整测试**

```bash
cd /Users/weiminglu/Projects/autonomous-improvement-loop
python3 -m pytest tests/ -q
```

---

## Task 2: 增强 plan_writer.py — Superpower 级 plan 格式

### 关键文件
- 修改: `scripts/plan_writer.py`

**增强目标**: plan 文档增加 `background`、`rollback`、`effort` 字段，并在文档中用醒目格式展示。

**Superpower plan 格式参考**:
```
# TASK-xxx · [标题]

> **Type**: idea/improve | **Source**: pm | **Effort**: medium

## Background
[2-3 句解释这个任务为什么重要，联系项目当前状态]

## Goal
[一句话目标]

## Why now
[具体动机，引用最近代码变化或项目状态]

## Scope
[具体文件/函数名]
- 要做: ...
- 不做: ...

## Relevant Files
- `scripts/init.py:cmd_trigger` — 改动位置
- `scripts/roadmap.py:load_roadmap` — 受影响

## Execution Plan
1. [Step 1: 具体操作，包括文件名和行号]
2. [Step 2: ...]

## Acceptance Criteria
- [ ] [可检验的标准 1]
- [ ] [可检验的标准 2]

## Verification
```bash
pytest tests/test_cli_integration.py -q
```

## Rollback
如果第 X 步出错：`git revert <commit>` 并删除相关改动

## Risks / Notes
- [已知风险及缓解方案]
```

### Steps

- [ ] **Step 1: 修改 write_plan_doc() 函数**

在 `scripts/plan_writer.py` 的 `write_plan_doc()` 中加入 `background`、`rollback`、`effort` 参数。

- [ ] **Step 2: 更新 plan 模板渲染**

将新字段加入 markdown 输出，使用上面列出的格式。

- [ ] **Step 3: 更新 task_planner.py 中所有候选的 plan 字段**

所有候选的 `PlannedTask` 要包含 `background`、`rollback`、`effort`。

- [ ] **Step 4: 测试生成的 plan 格式**

```bash
cd /Users/weiminglu/Projects/autonomous-improvement-loop
python3 -c "
from scripts.task_planner import choose_next_task
from scripts.roadmap import init_roadmap, load_roadmap
from scripts.plan_writer import write_plan_doc
from pathlib import Path
import tempfile

with tempfile.TemporaryDirectory() as tmp:
    plans = Path(tmp) / 'plans'
    plans.mkdir()
    roadmap_path = Path(tmp) / 'ROADMAP.md'
    init_roadmap(roadmap_path)
    roadmap = load_roadmap(roadmap_path)
    t = choose_next_task(Path('.'), roadmap, set(), 'zh')
    p = write_plan_doc(plans, 'TASK-TEST', t.title, t.task_type, t.source,
        context=t.context, why_now=t.why_now, scope=t.scope,
        non_goals=t.non_goals, relevant_files=t.relevant_files,
        execution_plan=t.execution_plan, acceptance_criteria=t.acceptance_criteria,
        verification=t.verification, risks=t.risks,
        background=getattr(t, 'background', ''),
        rollback=getattr(t, 'rollback', ''),
        effort=getattr(t, 'effort', 'medium'))
    print(p.read_text())
"
```

---

## Task 3: 修复 project_md.py — 真实 tech stack 检测

### 关键文件
- 修改: `scripts/project_md.py`

**问题**:
- `detect_tech_stack()` 用字符串包含检测，把注释里的关键词也匹配了
- "CLI 命令数: 0" 是错的（`@app.command(` 检测不适用于 typer）

**修复**:

1. `detect_tech_stack()`: 解析 Python 文件的 `import` / `from ... import` 语句，只检测真实导入
2. `detect_tech_stack()`: 加入对本项目真实使用的库检测：
   - `typer` (CLI framework)
   - `subprocess` (shell)
   - `pathlib` (path)
   - `re` (regex)
   - `git` (version control)
3. `count_cli_commands()`: 用 `@app.command(` 和 `@click.command` 双重检测
4. **增加项目洞察引擎**: 读取 `scripts/` 下每个文件的 docstring，生成"核心模块说明"
5. **增加变更统计**: 统计最近 30 天的 commit 数、文件改动数

### Steps

- [ ] **Step 1: 备份 project_md.py**

```bash
cp /Users/weiminglu/Projects/autonomous-improvement-loop/scripts/project_md.py \
   /Users/weiminglu/Projects/autonomous-improvement-loop/scripts/project_md.py.bak
```

- [ ] **Step 2: 重写 detect_tech_stack()**

只从真实的 import 语句检测，不从注释/字符串检测。

- [ ] **Step 3: 修复 count_cli_commands()**

同时检测 typer (`@app.command`) 和 click (`@click.command`)。

- [ ] **Step 4: 生成测试**

```bash
cd /Users/weiminglu/Projects/autonomous-improvement-loop
python3 -c "
from scripts.project_md import detect_tech_stack, count_cli_commands, count_source_files, count_tests
from pathlib import Path
p = Path('.')
print('tech_stack:', detect_tech_stack(p, 'software'))
print('cli_commands:', count_cli_commands(p))
print('source_files:', count_source_files(p))
print('tests:', count_tests(p))
"
```

预期输出：`tech_stack: Python + Typer + Subprocess + Pathlib + Git`

- [ ] **Step 5: 更新 `render_project_md()` — 加入模块说明和变更统计**

在 `核心能力` 表格上方加入：
```
## 最近动态（30天）
| 指标 | 数值 |
|------|------|
| 最近 commits | N |
| 源码文件变动 | N |
| 测试覆盖 | N% |
```
在 `核心能力` 表格中加入 `scripts/各模块名称` 的说明。

---

## Task 4: 将 PROJECT.md 更新加入 cron 工作流

### 关键文件
- 修改: `scripts/init.py` 中的 cron message 模板

**目标**: 每完成 3 个任务（或每 N 次迭代），自动更新 PROJECT.md，确保项目快照始终准确。

**实现方案**:
1. 在 `_record_result_only()` 或新函数 `_update_project_snapshot()` 中：
   - 读取当前 `VERSION` 文件获取版本号
   - 调用 `generate_project_md()` 更新 PROJECT.md
   - commit 并 push（只有内容变化才 commit）
2. 在 cron message 中加入步骤："如果完成 ≥3 个任务，执行 `python3 scripts/project_md.py --project . --output .ail/PROJECT.md`"

### Steps

- [ ] **Step 1: 在 init.py 中加入 `_maybe_update_project_md()` 函数**

```python
def _maybe_update_project_md(project: Path) -> None:
    """Update .ail/PROJECT.md if it doesn't exist or is stale.
    
    Called after result recording. Keeps project snapshot accurate.
    """
    from scripts.project_md import generate_project_md
    from scripts.init import ail_project_md
    project_md_path = ail_project_md(project)
    if not project_md_path.exists():
        generate_project_md(project, project_md_path, language="zh")
        ok("Generated initial PROJECT.md")
```

- [ ] **Step 2: 在 `_record_result_only()` 末尾调用**

在 `_record_result_only()` 的 `ok("Execution recorded...")` 之后，调用 `_maybe_update_project_md(project)`。

- [ ] **Step 3: 测试 PROJECT.md 生成**

```bash
cd /Users/weiminglu/Projects/autonomous-improvement-loop
python3 scripts/project_md.py --project . --output /tmp/PROJECT_TEST.md --language zh
head -60 /tmp/PROJECT_TEST.md
```

- [ ] **Step 4: 验证 PROJECT.md 在 cron 后更新**

运行 `a-trigger`，确认 `.ail/PROJECT.md` 时间戳更新。

---

## Task 5: 新建 test_task_planner.py — 保障 plan 质量

### 关键文件
- 新建: `tests/test_task_planner.py`

**测试用例**:

1. `test_choose_next_task_returns_different_titles_for_repeated_calls` — 连续 5 次调用 choose_next_task，每次返回不同 title（去重有效）
2. `test_plan_has_all_required_fields` — 每个生成的 PlannedTask 包含所有字段（background, rollback, effort, scope 等）
3. `test_scope_is_file_specific` — scope 包含具体文件路径，不只是 "CLI 集成测试"
4. `test_done_titles_excludes_passed_tasks` — 将已 pass 的 title 加入 done_titles 后，不返回该 title

### Steps

- [ ] **Step 1: 新建测试文件**

```bash
touch /Users/weiminglu/Projects/autonomous-improvement-loop/tests/test_task_planner.py
```

- [ ] **Step 2: 运行测试验证**

```bash
cd /Users/weiminglu/Projects/autonomous-improvement-loop
python3 -m pytest tests/test_task_planner.py -v
```

---

## Task 6: 端到端验证

- [ ] **Step 1: 完整测试套件**

```bash
cd /Users/weiminglu/Projects/autonomous-improvement-loop
python3 -m pytest tests/ -q
```

预期：全部通过（目标 45+ 测试）

- [ ] **Step 2: 运行 a-plan 观察生成的 plan 质量**

```bash
cd /Users/weiminglu/Projects/autonomous-improvement-loop
python3 scripts/init.py a-plan
```

检查输出：
- [ ] 有 `Background` section
- [ ] `Scope` 列出了具体文件/函数
- [ ] `Execution Plan` 有具体步骤
- [ ] `Effort` 标注了时间估计

- [ ] **Step 3: 运行 a-current 观察 PROJECT.md 快照准确性**

```bash
python3 scripts/init.py a-current
```

确认 tech stack、CLI 命令数、源码文件数正确。

- [ ] **Step 4: Commit 所有改动**

```bash
cd /Users/weiminglu/Projects/autonomous-improvement-loop
git add -A
git commit -m "feat: AI PM 级任务规划和项目快照质量升级"
```

---

## 验收标准

| 标准 | 验证方式 |
|------|---------|
| PROJECT.md tech stack 正确（Python + Typer + Subprocess） | `detect_tech_stack()` 输出验证 |
| CLI 命令数正确（≥10 个命令） | count_cli_commands() 输出验证 |
| TASK plan 有 Background/Scope/Execution Plan/Effort | 读取生成的 TASK-*.md 文件 |
| Scope 包含具体文件路径 | grep scope 结果验证 |
| 去重有效：已 pass 的 title 不重复生成 | 连续调用 choose_next_task |
| 全部测试通过 | `pytest -q` |
| PROJECT.md 在 cron 后自动更新 | 运行 a-trigger 前后对比 |

---

## 执行方式

**推荐: Subagent-Driven**
- 6 个 Task，每个 Task 由一个独立 subagent 完成
- 每个 Task 完成后本 session 审核，再继续下一个
- 优点：每个 Task 独立可验证，不会越改越乱

**请选择：**
1. Subagent-Driven（推荐，我派 6 个 subagent 分批执行）
2. Inline Execution（在这个 session 里顺序执行全部 6 个 Task）
