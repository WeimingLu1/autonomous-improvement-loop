# Autonomous Improvement Loop — 设计规格书

> 日期：2026-04-18
> 状态：草稿，待用户确认

---

## 核心理念

一个 agent 安装此 skill 后，即进入**自主研发守护模式**：持续监听队列，周期性执
行优先级最高的任务，汇报结果给用户。所有研发状态属于 skill，不污染项目代码库。

**设计原则**：
- 单项目制：一个 agent 只维护一个项目
- 队列串行化：用户和 cron 共享同一队列，不存在并发冲突
- AI 优先级：紧急破坏性 bug > 功能影响面 > 队列顺序
- 用户需求强制插队：无条件排在最前

---

## 1. 架构概览

```
[用户]  ←—— Telegram 汇报 ——┐
  ↑                            │
  │                            │
[Agent] ←—— cron 触发 —— [OpenClaw Cron]
  │                            │
  │                         isolated session
  │                         (timeout: 1h)
  │                            │
  └──── 共享队列 ←──────────────┘
                   │
                   ├── HEARTBEAT.md（队列）
                   ├── DEVLOG.md（已完归档）
                   └── scripts/（自动化脚本）
```

**关键约束**：
- cron 和用户共用同一个 agent session
- cron 触发时 agent 在 isolated session 中运行（不干扰用户当前对话）
- 汇报通过 OpenClaw announce 机制回到用户当前会话

---

## 2. 队列系统（HEARTBEAT.md）

队列文件位于 skill 目录内：`~/.openclaw/workspace-YOUR_AGENT/skills/autonomous-improvement-loop/HEARTBEAT.md`

### 2.1 条目结构

```markdown
## Queue

| # | 类型 | 优先级分 | 内容 | 来源 | 状态 | 创建时间 |
|---|------|----------|------|------|------|----------|
| 1 | bug | 92 | [[Bug]] 用户无法登录时崩溃 | user | pending | 2026-04-18 |
| 2 | feature | 78 | [[Feature]] 导出 PDF 报告 | user | pending | 2026-04-17 |
| 3 | improve | 65 | [[Improve]] 补齐 auth.py 单元测试 | scanner | pending | 2026-04-16 |
```

**字段说明**：
- `#`：自动编号
- `类型`：bug | feature | improve
- `优先级分`：0-100，AI 计算（见 2.2）
- `内容`：`[[Type]] 具体描述`
- `来源`：user（用户提交）| scanner（自动扫描）| system（内置任务）
- `状态`：pending | in_progress | done | skip
- `创建时间`：YYYY-MM-DD HH:MM

### 2.2 优先级评分算法

```
score = urgency_score × 0.5 + impact_score × 0.3 + dependency_score × 0.2

用户请求：score = 100（强制插队，所有其他任务下移）

urgency_score（紧急度，0-100）：
  - 破坏核心功能的 bug：90-100
  - 破坏非核心功能的 bug：70-89
  - 普通 feature/improve：50（基准分）

impact_score（影响面，0-100）：
  - 影响所有用户的 bug：90-100
  - 影响多数用户的 bug：70-89
  - 部分用户的 feature：50-69
  - 内部改进（测试、文档）：30-49

dependency_score（依赖度，0-100）：
  - 被多个任务依赖：90-100
  - 被1个任务依赖：60-89
  - 无依赖：30（基准分）
```

**队列重排序规则**：
- 每次添加新条目后，队列按 score 降序重新排序
- 用户请求添加时，直接置顶，后续条目顺序保持
- score 相等时，在队列时间更早的优先

### 2.3 Run Status（在 HEARTBEAT.md 顶部）

```markdown
## Run Status

| 字段 | 值 |
|------|----|
| last_run_time | 2026-04-18 17:28:10 CST |
| last_run_commit | `15c76ec` |
| last_run_result | pass |
| last_run_task | #1 [[Bug]] 用户无法登录时崩溃 |
| rollback_on_fail | true |
| cron_lock | false |
```

- `cron_lock: true` 时，agent 拒绝处理用户直接发起的文件修改（队列串行化保证）
- `cron_lock` 在 cron session 开始时设为 true，结束后设为 false

---

## 3. 用户请求处理

### 3.1 用户发起请求

用户通过对话发送任务（如"修一下 XXX bug"或"加一个 XXX 功能"）：

1. agent 将请求加入队列（user 来源）
2. 优先级分强制设为 100（插队）
3. 立即向用户确认：`✅ 已加入队列，优先级：最高（#1）`
4. 不中断当前 cron 执行（如果 cron 正在运行）
5. cron 下次运行时按新队列顺序执行

### 3.2 队列串行化（无锁实现）

```
用户发起请求 → 检查 Run Status.cron_lock
  ├─ cron_lock == false → 立即执行或加入队列
  └─ cron_lock == true  → 加入队列，回复用户"cron 正在运行，已插队"
```

由于 cron 使用 isolated session 与用户会话隔离，同一时刻只有一个执行流，无需
文件锁。cron_lock 是状态标识，不是互斥锁。

---

## 4. Cron 执行流程（isolated session）

```
cron 触发（每 30 分钟，isolated session，1 小时 timeout）
    │
    ▼
① cron_lock = true
    │
    ▼
② python scripts/run_status.py write ... result=starting
    │
    ▼
③ 读取 HEARTBEAT.md Queue
    │
    ▼
④ AI 重新评分 + 排序
    │
    ▼
⑤ 执行队列顶部任务
    │   ├─ pytest 失败 → 识别为 #bug，优先修
    │   │                 修好后 pytest → commit → push → 继续
    │   │
    │   └─ pytest 通过 → 实现 feature/improve
    │                     实现完 → pytest → commit → push
    │
    ▼
⑥ 更新 docs（README.md、docs/agent/ 等）
    │   └─ verify_cli_docs.py 检查文档一致性
    │
    ▼
⑦ Release（VERSION bump → git tag → gh release）
    │
    ▼
⑧ cron_lock = false
    │
    ▼
⑨ python scripts/run_status.py write result=pass
    │
    ▼
⑩ announce 汇报给用户当前 session
    │
    ▼
⑪ project_insights.py（1 个新候选）
    │
    ▼
⑫ memory 更新
    │
    ▼
stop（等待下次 cron 触发）
```

---

## 5. GitHub 提交与 Release

每次完成任务后：

```bash
# 代码提交
git add . && git commit -m "feat(#N): 简短描述" && git push

# Release
VERSION=$(cat VERSION)
git tag -a v${VERSION} -m "Release v${VERSION}"
git push origin v${VERSION}
gh release create "v${VERSION}" --generate-notes --repo OWNER/REPO
next=$((VERSION + 1))
echo ${next} > VERSION
git add VERSION && git commit -m "chore: bump version" && git push
```

**注意**：`gh` CLI 需提前认证。skill 安装时检查 `gh auth status`。

---

## 6. 自动化脚本（scripts/）

所有脚本项目无关，通过参数传入项目路径。

| 脚本 | 作用 |
|------|------|
| `run_status.py` | 读写 Run Status（含 cron_lock） |
| `project_insights.py` | 扫描项目，追加 1 个候选到队列 |
| `verify_cli_docs.py` | 校验 CLI vs README 一致性 |
| `verify_and_revert.py` | push → verification_command → 失败自动 git revert |
| `priority_scorer.py` | AI 优先级评分（新增）|

---

## 7. Skill 配置（config.md）

skill 目录下的 `config.md` 是唯一的项目配置：

```markdown
# Autonomous Improvement Loop — 项目配置

## 项目路径
project_path: ~/Projects/YOUR_PROJECT

## GitHub 仓库
repo: https://github.com/OWNER/REPO

## 版本文件
version_file: ~/Projects/YOUR_PROJECT/VERSION

## 文档目录
docs_agent_dir: ~/Projects/YOUR_PROJECT/docs/agent

## OpenClaw Agent ID
agent_id: YOUR_AGENT_ID

## Telegram Chat ID
chat_id: YOUR_CHAT_ID

## Cron 配置
cron_schedule: "*/30 * * * *"
cron_timeout: 3600  # 1 小时
```

**安装时**：填写 config.md，即完成项目绑定。

---

## 8. 文件结构

```
autonomous-improvement-loop/
├── SKILL.md                    # 主技能说明
├── config.md                   # 项目配置文件（安装时填写）
├── HEARTBEAT.md                # 队列 + Run Status（由 skill 管理）
├── DEVLOG.md                   # 已完成任务归档
├── specs/
│   └── autonomous-improvement-loop-design.md
├── scripts/
│   ├── run_status.py           # 读写 Run Status（含 cron_lock）
│   ├── project_insights.py        # 扫描项目，追加 1 个候选
│   ├── priority_scorer.py      # AI 优先级评分
│   ├── verify_cli_docs.py      # 校验 CLI vs README
│   └── verify_and_revert.py # push → verification_command → 自动回滚
├── references/
│   ├── file-templates.md
│   └── checklist.md
└── prompts/
    ├── QUEUE_SYSTEM_PROMPT.md   # agent 的队列系统提示词
    └── CLEANUP_CHECKLIST.md    # 提交前自查清单
```

---

## 9. 与项目目录的关系

skill 所有状态文件都在 skill 目录内，**不污染项目目录**。

项目目录（`~/Projects/YOUR_PROJECT/`）仅存放：
- 项目的业务代码
- `docs/agent/`（由 cron 执行时同步更新）

---

## 10. 依赖与前提条件

- [ ] `gh` CLI 已认证
- [ ] 项目已 clone 到本地
- [ ] `VERSION` 文件存在于项目根目录
- [ ] `docs/agent/` 目录存在于项目内
- [ ] Python venv 存在于 `.venv/`
- [ ] `pytest -q` 能正常运行

---

## 11. 开放问题（已解决）

- **announce 机制**：cron job 配置时通过 `--announce --channel telegram --to CHAT_ID` 自动路由到用户当前 session，无需手动指定 session ID
- **LLM 评分**：priority_scorer.py 调用 agent 自身的 LLM 直接计算 score，输出带解释的 JSON，无需额外 API
- **DEVLOG.md**：保留，在 skill 文件夹内，记录每个 agent-skill 组合对应的项目研发日志（skill = agent × 项目，1:1 绑定）
