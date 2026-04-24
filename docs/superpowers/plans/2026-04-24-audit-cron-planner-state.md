# AIL 调度/规划/状态一致性修复计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修复 AIL 在 cron、ROADMAP 状态流转、plan 重复生成上的系统性问题，避免重复调度、重复 plan、current task 脏状态再次出现。

**Architecture:** 先做止血（cron 单实例 + current task 清理），再做 planner/persistence 的重复标题硬约束，最后补健康指标和复审。整个过程按三轮 audit -> fix -> re-audit 推进，每轮都用测试和状态检查作为硬证据。

**Tech Stack:** Python, pytest, OpenClaw CLI, markdown state files (`.ail/ROADMAP.md`), git history inspection

---

### Task 1: 调度与状态止血

**Files:**
- Modify: `scripts/cron.py`
- Modify: `scripts/state.py`
- Modify: `scripts/cli.py`
- Modify: `scripts/roadmap.py`
- Test: `tests/test_cli_integration.py`

- [ ] **Step 1: 审计现有 cron 单实例与 current task 清理逻辑**

Run:
```bash
cd /Users/weiminglu/Projects/autonomous-improvement-loop
openclaw cron list
python3 scripts/init.py a-status
python3 - <<'EOF'
from pathlib import Path
from scripts.roadmap import load_roadmap
r = load_roadmap(Path('.ail/ROADMAP.md'))
print(r.current_task)
print(r.post_feature_maintenance_remaining, r.maintenance_anchor_title)
EOF
```
Expected: 能复现或确认 active cron 数量、current task 是否可能为 done、maintenance anchor 是否残留。

- [ ] **Step 2: 为 cron 启动加“同名 AIL cron 单实例”保护**

在 `scripts/cron.py` / `scripts/state.py` 中实现：
```python
# 目标行为
# - detect 所有同名 cron，而不是只认一个
# - 若发现多个，默认清理多余实例
# - config 中只保留最终生效的一个 cron_job_id
```

- [ ] **Step 3: 为 current task 引入 done 清理规则**

在 `scripts/cli.py` / `scripts/roadmap.py` 中实现：
```python
# 目标行为
# - 若 Current Task.status in {'done', 'pass'} 或已明显结束，不再把它保留在 Current Task 区
# - maintenance 结束后，maintenance_anchor_title 必须清空
```

- [ ] **Step 4: 增加回归测试覆盖状态止血场景**

测试至少覆盖：
```python
# current task 为 done 时，a-status / trigger 路径不会继续把它视为活跃任务
# 多个 cron 存在时，启动逻辑不会留下双实例
```

- [ ] **Step 5: 跑 targeted tests**

Run:
```bash
cd /Users/weiminglu/Projects/autonomous-improvement-loop
python3 -m pytest tests/test_cli_integration.py -q
```
Expected: 与状态流转相关测试通过。

### Task 2: Planner 与 plan 写入防爆炸

**Files:**
- Modify: `scripts/cli.py`
- Modify: `scripts/task_planner.py`
- Modify: `scripts/task_ids.py` (if needed)
- Test: `tests/test_task_planner.py`
- Test: `tests/test_cli_integration.py`

- [ ] **Step 1: 审计重复 title 在“选择期”和“写入期”的脱节点**

Run:
```bash
cd /Users/weiminglu/Projects/autonomous-improvement-loop
python3 - <<'EOF'
from pathlib import Path
import re, collections
ctr=collections.Counter()
for p in (Path('.ail')/'plans').glob('TASK-*.md'):
    try:
        first=p.read_text(encoding='utf-8').splitlines()[0].strip()
    except Exception:
        continue
    m=re.match(r'#\s+TASK-\d+\s+·\s+(.+)$', first)
    if m:
        ctr[m.group(1)] += 1
print('plan_count', sum(ctr.values()))
print('unique_titles', len(ctr))
print('top_dupes', ctr.most_common(10))
EOF
```
Expected: 明确看到重复标题现状，作为修复前基线。

- [ ] **Step 2: 增加 active/current/reserved/plan 文件级别的重复标题硬约束**

在 `scripts/cli.py` 和必要时 `scripts/task_planner.py` 中实现：
```python
# 目标行为
# - 如果同标题任务已经存在于 current task / reserved user task / 未消费的 plan docs 中
#   则不再新建新的 TASK-xxx plan 文件
# - planner 选出来的标题，在落盘前再做一次硬校验
```

- [ ] **Step 3: 增加重复标题生命周期测试**

测试至少覆盖：
```python
# 同标题 plan 已存在 -> a-plan --force 不应继续生成新的 TASK-ID
# 维护任务在 active state 中存在时，不应再次创建副本
```

- [ ] **Step 4: 跑 targeted tests**

Run:
```bash
cd /Users/weiminglu/Projects/autonomous-improvement-loop
python3 -m pytest tests/test_task_planner.py tests/test_cli_integration.py -q
```
Expected: planner 相关测试通过，没有新的重复生成回归。

### Task 3: 健康指标、终审与全量验证

**Files:**
- Modify: `scripts/cli.py`
- Modify: `scripts/state.py` (if needed)
- Test: `tests/test_cli_integration.py`

- [ ] **Step 1: 为 a-status 增加 planner/plan 健康指标**

目标输出至少包含：
```text
active_cron_count
plan_count
unique_plan_titles
duplicate_plan_ratio
top_duplicate_titles (top 3 or top 5)
```

- [ ] **Step 2: 用当前仓库做一次终审检查**

Run:
```bash
cd /Users/weiminglu/Projects/autonomous-improvement-loop
openclaw cron list
python3 scripts/init.py a-status
python3 -m pytest tests/ -q
```
Expected: cron 停止/受控、status 输出健康度、全量测试通过。

- [ ] **Step 3: 记录修复前后对比**

至少记录：
```text
- 修复前: plan_count / unique_titles / top duplicate titles
- 修复后: 新生成策略是否阻止重复写入
- current task 是否仍可能残留 done 状态
- active cron count 是否可见且受控
```

- [ ] **Step 4: 提交最终修复**

Run:
```bash
git add scripts/ tests/ docs/superpowers/specs/2026-04-24-audit-cron-planner-state-design.md docs/superpowers/plans/2026-04-24-audit-cron-planner-state.md
git commit -m "fix: harden cron, roadmap state, and task planning dedupe"
```
Expected: 所有三轮修复纳入一次清晰提交历史（或按轮次拆分提交）。
