# AIL 调度/规划/状态一致性审计设计

## 背景

2026-04-24 凌晨，autonomous-improvement-loop 出现了明显的系统性异常：

- 同时存在两个 cron job，导致重复调度
- `.ail/plans/` 积累到 527 个 plan 文件，但只有 49 个唯一标题
- `ROADMAP.md` 的 Current Task 区保留了 `status=done` 的任务，状态不一致
- task planner 在候选耗尽、sticky done、maintenance rhythm 等边界场景下仍会重复生成历史任务

这些问题说明：当前系统不是单点 bug，而是调度层、状态层、任务选择层共同失稳。

## 目标

把系统修回到“可持续运行、可审计、不会爆号”的状态，重点达成：

1. 任意时刻只允许一个有效 cron
2. `ROADMAP.md` 不再保留 `done` 状态的 current task
3. plan 生成必须对重复标题有硬约束，不能无限增殖
4. `a-status` 能直观看到重复度/健康度
5. 用三轮 audit -> fix -> re-audit 逐步收敛，而不是一次性盲改

## 方案选型

### 方案 A：只修触发层（最小改动）
- 仅修 cron 去重和 current task 清理
- 优点：快
- 缺点：plan 爆炸和重复 title 仍会持续

### 方案 B：调度 + 状态 + planner 一起修（推荐）
- cron 启动时做单实例保护
- `ROADMAP` 状态流转做一致性修复
- plan 写入前增加重复 title 硬校验
- 暴露健康指标便于后续观察
- 优点：能真正解决昨晚的问题链条
- 缺点：涉及多文件联动，需要仔细验证

### 方案 C：直接重做 planner
- 重写候选选择和状态机
- 优点：理论上最干净
- 缺点：风险太大，不适合当前救火场景

**采用：方案 B。**

## 设计

### 1. Cron 单实例保护
- `a-start` / `create_cron()` 启动前，不再只是“发现 existing 就询问是否复用”
- 对“同名 AIL cron”做强约束：默认保留 1 个，清理重复项
- `a-status` 显示 active cron count；count > 1 直接标红/警告

### 2. ROADMAP 一致性修复
- 引入“current task 清理”规则：
  - 若 current task 已 `done` / 已被记录为完成，则从 Current Task 区清空
  - `maintenance_anchor_title` 在 maintenance 结束后必须清空
- 修复 `a-status` / trigger 链路，确保不会长期停在 `done` current task

### 3. Plan 反爆炸保护
- 在 `a-plan` / `_generate_next_task()` / 写 plan 之前增加硬校验：
  - 若标题已存在于 active/current/reserved/plans 且没有明确允许复用，就不再创建新 TASK-ID
- 将“标题去重”从 planner 选择期扩展到写入期，避免 selection 和 persistence 脱节
- 增加 plan 健康指标：plan 总数、unique title 数、重复率、top duplicate titles

### 4. 三轮修复节奏

#### Cycle 1 — 调度与状态止血
- 修 cron 单实例
- 修 current task 清理
- 修状态报告

#### Cycle 2 — Planner 与 plan 写入防爆炸
- 修重复标题硬约束
- 修计划文件重复创建
- 补测试覆盖

#### Cycle 3 — 健康度与最终复审
- `a-status` 加健康指标
- 全量复审重复率和 state consistency
- 做一次最终验证，确认没有回归

## 影响范围

- `scripts/cron.py`
- `scripts/state.py`
- `scripts/cli.py`
- `scripts/roadmap.py`
- `scripts/task_planner.py`
- `tests/test_cli_integration.py`
- `tests/test_task_planner.py`
- 可能新增专门的状态/健康度测试

## 风险与控制

### 风险 1：修重复 title 时误伤合法复用任务
控制：只阻止“当前活跃/现有 plans 中的重复写入”；对 Done Log 中允许保留历史，但要更谨慎地重新选择

### 风险 2：清 current task 影响 trigger 流程
控制：补端到端测试，覆盖 done -> clear -> next task 生成

### 风险 3：多处状态字段联动导致回归
控制：每一轮修完立即跑 targeted tests + full test suite，再进入下一轮

## 验收标准

1. `openclaw cron list` 不再出现双 AIL cron（启动逻辑有保护）
2. `a-status` 不再把 `done` task 当 current task 显示
3. 新 plan 不再对同一标题疯狂生成新 TASK-ID
4. 针对昨晚问题新增测试，且全量测试通过
5. 三轮 audit/fix/re-audit 后，重复生成率显著下降并有命令输出可观测
