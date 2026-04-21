# Autonomous Improvement Loop PM Roadmap Refactor Design

## Goal

将 autonomous-improvement-loop 从“滚动任务队列 + 扫描器”重构为“AI 项目经理 + 单当前任务 + Plan 驱动执行”系统。

系统不再维护一个 6 项滚动队列，而是始终维护 1 个当前任务。每个任务都必须先生成结构化 plan 文档，再允许进入执行阶段。cron 和 `a-trigger` 仅按 plan 执行，不再依赖一句话任务描述推断实现方式。

---

## Why This Refactor

现有模型存在以下根本问题：

1. **任务过于泛化**
   `[[Idea]] 审视项目...`、`[[Improve]] Add integration tests...` 这类任务标题更像启发式提示，不像 PM 输出的可执行开发任务。

2. **Queue 承载了过多语义**
   目前 queue 同时承担 backlog、优先级、执行输入、历史上下文入口等角色，导致内容越来越粗糙。

3. **执行阶段上下文不足**
   cron 执行任务时依赖一行 queue 文本，不足以支撑高质量研发执行。

4. **PM 角色缺失**
   系统现在更像扫描器，不像项目经理。它没有先阅读 `PROJECT.md`、历史日志、当前代码状态，再做任务规划。

5. **用户需求入口不统一**
   `a-add` 只是插入一行队列，而不是把用户需求转成正式任务文档。

这次重构的目标是把系统改造成：

- `ROADMAP.md` 负责状态与历史
- `plans/TASK-xxx.md` 负责任务定义
- PM 负责决定当前最合理的任务
- Executor 负责严格按 plan 执行

---

## High-Level Architecture

### Core model

系统拆成三层：

1. **Roadmap layer**
   `ROADMAP.md` 保存当前任务指针、节奏状态、最近决策摘要、Done Log。

2. **Plan layer**
   `plans/TASK-xxx.md` 保存每个任务的完整定义，是任务唯一可信来源。

3. **Execution layer**
   cron / `a-trigger` 只读取当前 task_id，然后按对应 plan 执行。

### Behavioral model

- 系统始终只保留 **1 个当前任务**
- 每次 PM 只生成 **1 个新任务 + 1 个 plan doc**
- 默认节奏是 **idea → improve → improve**
- 如果有用户需求，用户需求优先，但不打断正在执行的任务
- 当当前任务完成后，再生成下一任务

---

## File Structure

### New / renamed control files

- `ROADMAP.md`
  - 取代 `HEARTBEAT.md`
  - 负责保存当前任务状态、节奏状态、决策摘要、Done Log

- `plans/`
  - 平铺任务计划文档
  - 示例：
    - `plans/TASK-001.md`
    - `plans/TASK-002.md`

### Supporting scripts

建议新增或重组：

- `scripts/roadmap.py`
  - 读取、写入、初始化 `ROADMAP.md`
- `scripts/task_ids.py`
  - 分配 `TASK-001` 这类稳定 ID
- `scripts/task_planner.py`
  - PM 规划器，读取项目上下文后决定下一个任务
- `scripts/plan_writer.py`
  - 把 PM 选择的任务写成标准 plan 文档
- `scripts/current_task.py`
  - 获取 / 设置当前任务
- `scripts/roadmap_migration.py`
  - 旧 `HEARTBEAT.md` → 新 `ROADMAP.md` 的清理/初始化

现有 `inspire_scanner.py`、旧 queue parser、rolling-refresh 逻辑将降级为内部素材采集器，或被部分替换。

---

## ROADMAP.md Format

`ROADMAP.md` 不再保存 backlog 队列，而是保存唯一 current task 和历史记录。

建议结构如下：

```markdown
# Roadmap

## Current Task

| task_id | type | source | title | status | created |
|--------|------|--------|-------|--------|---------|
| TASK-001 | idea | pm | 为 CLI 增加任务文档回显能力 | pending | 2026-04-21 |

## Rhythm State

| field | value |
|------|-------|
| next_default_type | improve |
| improves_since_last_idea | 0 |
| current_plan_path | plans/TASK-001.md |
| reserved_user_task_id | TASK-002 |

## PM Notes

- 最近一次规划基于 PROJECT.md、最近 Done Log、测试覆盖率和 CLI 使用路径生成
- 用户需求优先于新的 PM 任务，但不打断正在执行中的任务

## Done Log

| time | task_id | type | source | title | result | commit |
|------|---------|------|--------|-------|--------|--------|
| 2026-04-21T02:11:00Z | TASK-001 | improve | pm | 修复 a-status 子进程死锁 | pass | 3b8768f |
```

### Notes

- 只保留一个 Current Task
- 不再有 `score`
- 不再有 `detail`
- 不再有 6 项 queue
- `reserved_user_task_id` 用于表达“用户需求已生成，但当前 doing 任务不能被打断”

---

## Task Plan Document Format

每个任务都必须对应一个 `plans/TASK-xxx.md`。

推荐结构：

```markdown
# TASK-001 · 为 CLI 增加任务文档回显能力

- Type: idea
- Source: pm
- Status: pending
- Created: 2026-04-21

## Goal
一句话说明最终交付结果。

## Context
说明该任务是根据什么项目现状、用户路径、历史任务得出的。

## Why now
为什么当前应该优先做这个任务。

## Scope
本次明确要做的内容。

## Non-goals
本次明确不做的内容。

## Relevant Context
- 相关文件
- 相关模块
- 相关测试
- 相关历史任务

## Execution Plan
分步骤执行方案，偏 PM / eng handoff 风格。

## Acceptance Criteria
完成标准。

## Verification
需要运行的验证命令。

## Risks / Notes
风险、注意事项、边界。
```

### Requirement

当用户运行：
- `a-plan`
- `a-current`

除了显示当前任务摘要，还必须**直接回显完整 plan doc 内容**，方便用户立即查看，不需要再手动打开文件。

---

## PM Planning Logic

### Inputs

PM 规划器每次生成新任务前，必须至少参考：

1. `PROJECT.md`
2. `ROADMAP.md`
3. `Done Log`
4. 当前代码结构与重要文件
5. 测试状态 / 文档状态 / 版本状态
6. 用户最近手动提出的需求（若存在）

### PM output requirements

PM 不能再输出泛化任务，比如：

- 审视项目找出用户痛点
- Add tests for critical paths
- Improve docs

除非后面给出非常具体的执行方案，并写入 plan 文档。

PM 必须输出：

- 一个明确 task_id
- 一个明确任务标题
- 任务类型（idea / improve）
- 任务来源（pm / user）
- 一份完整 plan 文档

### Deduplication rules

必须避免重复生成：

- 已完成任务（Done Log 中已有）
- 当前任务相同主题
- 仅换说法但本质相同的任务
- 与最近 1-2 个任务高度重复的维护项

去重不能只靠字符串匹配，应组合：

- task title 归一化
- plan goal 归一化
- 与 Done Log 主题比对
- 与当前 `PROJECT.md` 中已完成能力比对

### Rhythm rules

默认节奏：

- idea
- improve
- improve

但这不是模板句子的切换，而是任务类型的节奏。

- `idea` 必须偏创新 / 研发 / 新功能 / 新能力
- `improve` 必须偏维护 / 测试 / 文档 / 重构 / 稳定性

PM 需要在每次规划时记录节奏状态，而不是生成固定句式候选项。

---

## User Request Handling (`a-add`)

`a-add "一句需求"` 的新语义：

1. 接收用户一句自然语言需求
2. 立即生成新的 `TASK-xxx`
3. 生成完整 plan doc
4. 标记 `source=user`
5. 若当前任务状态是 `doing`：
   - 不打断当前执行
   - 把用户任务记录为 `reserved_user_task_id`
   - 保证它成为下一个任务
6. 若当前任务为空或只是 `pending`：
   - 用户任务直接成为当前任务

### Important invariant

**用户需求一定优先执行**。

但用户已明确选择：
- 不打断正在执行中的任务
- 当前 doing 任务完成后，用户任务必须立刻成为 next task

---

## Command Redesign

### Keep

- `a-status`
- `a-trigger`
- `a-add`
- `a-start`
- `a-stop`
- `a-log`
- `a-config`

### Redesign

- `a-refresh` → `a-plan`
  - 生成当前任务和 plan
  - 若已有当前任务，可用 `--force` 重写

- `a-queue` → `a-current`
  - 查看当前任务
  - 同时回显完整 plan doc

### Deprecate

- `a-scan`
- `a-clear`

### Backward-compatible aliases

- `a-refresh` 可暂时 alias 到 `a-plan`
- `a-queue` 可暂时 alias 到 `a-current`

---

## Execution Flow

### `a-plan`

1. 读取 `ROADMAP.md`
2. 如果当前已有 `pending` / `doing` 任务：
   - 默认不重建
   - 除非 `--force`
3. PM 读取项目上下文
4. 生成一个新的 `TASK-xxx`
5. 写入 `plans/TASK-xxx.md`
6. 更新 `ROADMAP.md` 的 Current Task
7. 返回当前任务摘要 + 完整 plan doc 内容

### `a-current`

1. 读取 `ROADMAP.md`
2. 获取当前 task_id
3. 读取对应 plan 文档
4. 返回任务摘要 + 完整 plan doc 内容

### `a-trigger` / cron

1. 读取当前任务
2. 找到对应 `plans/TASK-xxx.md`
3. 把 plan 作为严格执行指令
4. 执行任务
5. 写 Done Log
6. 更新节奏状态
7. 若存在 `reserved_user_task_id`：
   - 把该任务提升为 current task
   - 否则让 PM 生成下一个任务

---

## Migration Strategy

用户已明确表示：

- 不在乎保留旧历史
- 可以清空旧记录

因此推荐最简单的迁移：

1. 删除旧 `HEARTBEAT.md` 的 queue 语义
2. 新建 `ROADMAP.md`
3. 清空旧 queue / old done log / old rhythm state
4. 从 `TASK-001` 重新编号
5. 保留 `PROJECT.md`
6. 删除或降级旧 scanner-based backlog 逻辑

这样可以避免兼容旧格式带来的复杂性。

---

## Testing Strategy

至少要覆盖：

1. `a-plan` 在空状态下生成 `TASK-001` + `plans/TASK-001.md`
2. `a-current` 返回当前任务并回显完整 plan doc
3. `a-add` 能生成用户任务 plan
4. `a-add` 在当前 `doing` 任务存在时，写入 reserved user task
5. `a-trigger` 按 plan 执行，而不是按标题执行
6. Done Log 新表结构写入正确
7. rhythm 状态正确维持 idea → improve → improve
8. PM 生成任务时不会重复 Done Log 中已完成主题
9. `a-refresh` / `a-queue` 旧命令 alias 正常工作
10. migration 初始化会清理旧 heartbeat 状态并创建新 roadmap

---

## Risks

1. **LLM 规划质量波动**
   需要用清晰 prompt 约束 PM 输出格式，否则计划会过虚。

2. **去重语义复杂**
   不能只靠字符串比较，至少要有轻量主题归一化。

3. **执行与计划脱节**
   cron executor 必须明确要求“严格按 plan 执行”，否则还是会回到一句话任务模式。

4. **命令迁移期混乱**
   需要短期兼容 alias，避免旧使用方式立刻失效。

---

## Recommended Rollout

### Phase 1
- 新增 `ROADMAP.md`
- 新增 `plans/`
- 实现 `a-plan` / `a-current`
- 新 done log 结构
- 基础 PM planner

### Phase 2
- 重写 `a-add`
- 重写 cron execution flow
- 用户任务优先级机制

### Phase 3
- 废弃 old queue / scanner-first logic
- 清理 `a-scan` / `a-clear`
- 完成迁移和兼容层收尾

---

## Recommendation

采用彻底重构方案（方案 2）。

这是最符合目标的结构：
- Queue 不再假装是 PM 文档
- PM 真正负责规划
- Executor 真正负责执行
- 用户需求与系统任务统一进入 task/plan 模型
- 任务只保留一个 current task，系统行为更清晰可控
