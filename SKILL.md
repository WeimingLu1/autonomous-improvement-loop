# Autonomous Improvement Loop — Skill Reference

## 概述

这是 AI 时代的"通用型持续改进循环"。它驱动一个持续运转的工作流：
**维护任务队列 → 挑选最高优先级 → 执行 → 验证 → 记录进度 → 重复**

设计为**类型无关（type-agnostic）** — 支持软件、写作、视频、研究或任意长期项目。

---

## 核心概念

### 项目类型（project_kind）

Skill 会自动检测项目类型，也可以在 `config.md` 中手动指定：

| 类型 | 说明 | 示例 |
|------|------|------|
| `software` | 代码项目 | CLI工具、Web服务、库 |
| `writing` | 写作/文字项目 | 小说、博客、技术文章 |
| `video` | 视频/媒体项目 | 短片、纪录片、素材管理 |
| `research` | 学术/研究项目 | 论文、文献综述 |
| `generic` | 通用项目 | 任意长期工作 |

**自动检测**：队列扫描器 (`project_insights.py`) 通过目录结构和文件类型自动判断项目种类，无需配置即可工作。

### 改进循环生命周期

```
┌──────────────────────┐
│  Cron 触发（每30分钟） │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ project_insights.py  │  ← 扫描项目类型，生成改进建议
│  (通用发现器)         │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│  从队列取最新任务      │
│  （优先级最高）        │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│  Agent 执行任务       │
│  提交 Commit         │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│ verify_and_revert.py │  ← 验证结果，失败则回滚
│  (验证钩子)          │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│  更新队列 + 报告       │
│  Telegram / GitHub   │
└──────────────────────┘
```

---

## HEARTBEAT.md 结构

```
## Run Status         ← 运行时状态
## Queue              ← 任务队列（核心工作区）
## Done Log           ← 已完成任务日志
---
```

### Run Status 字段

| 字段 | 说明 |
|------|------|
| `last_run_time` | 最近一次运行时间 |
| `last_run_commit` | 最近一次 commit hash |
| `last_run_result` | `pass` / `fail` / `unverified` |
| `last_run_task` | 最近任务的描述 |
| `cron_lock` | `true` = 有人在修改队列，跳过本次 Cron |
| `mode` | `bootstrap` / `normal` |
| `rollback_on_fail` | `true` = 任务失败时自动回滚 |

### Queue 格式

```
| # | Type | Score | Content | Source | Status | Created |
|---|------|-------|---------|--------|--------|---------|
| 1 | improve | 72 | [[Improve]] 为未测试的模块补齐单元测试 | scanner | done | 2026-04-18 |
```

- **Type**：`improve` / `feature` / `fix` / `wizard` / `user`
- **Score**：优先级分数（越高越先执行）
- **Source**：`scanner` / `user` / `agent`
- **Status**：`pending` / `done` / `skip`

---

## 队列驱动流程

### 用户请求插入任务

用户通过消息请求任务 → 直接写入 HEARTBEAT.md Queue 区（优先级 100，标记 `user`）

### Cron 自动执行

1. **Cron** 每 30 分钟触发一个隔离 Agent Session
2. Session 读取 `skills/autonomous-improvement-loop/SKILL.md`
3. 按 SKILL.md 内指令执行循环

---

## 脚本说明

| 脚本 | 职责 | 输入 |
|------|------|------|
| `project_insights.py` | 扫描项目类型，生成改进建议 | `--project`, `--heartbeat`, `--language` |
| `init.py` | 接管已有项目 / 初始化新项目 / 查看状态 | adopt / onboard / status |
| `verify_and_revert.py` | 执行验证命令，失败则自动回滚 | `--project`, `--heartbeat`, `--commit`, `--task` |
| `priority_scorer.py` | 优先级评分（支持用户请求插队） | stdin/stdout HEARTBEAT 格式 |
| `run_status.py` | 读写 Run Status 区 | `--heartbeat`, `read`/`write` |

---

## 验证与回滚

`verify_and_revert.py` 读取 `config.md` 中的 `verification_command`：

- **空** → 无自动验证，仅标记 `unverified`，需要人工确认
- **配置了命令** → 执行，成功则写 `pass`，失败则自动回滚上一次 commit

不再强制绑定 pytest — 任何可执行的 shell 命令都可以作为验证命令。

---

## 报告模板（Telegram）

```markdown
📋 项目改进报告 — {project_name}

完成: {done_count} 个任务
耗时: {duration}
结果: {result}

{if failures}:
⚠️ 失败:
{list}
{/if}

{if unverified}:
⚠️ 未验证，需要人工检查
{/if}

下一任务: {next_task}
轮次: {iteration}
```

---

## 项目类型与改进建议对照

### software（代码项目）
- 单元测试覆盖、文档、TODO/FIXME 处理
- CLI 体验、配置管理、错误提示
- 智能功能（建议、检测）、数据导入导出
- 成就/连续系统

### writing（写作项目）
- 情节一致性、角色弧线、节奏审查
- 对话自然性、场景目标与张力
- 结构完整性、章节钩子
- 术语一致性、可读性

### video（视频/媒体项目）
- 脚本结构、镜头语言、过渡
- 节奏/情绪弧线、连续性（道具/服装/时间线）
- 音效/音乐 cue、旁白质量
- 剪辑点、B-roll 覆盖

### research（学术/研究项目）
- 论文结构、引言/方法/结果/讨论完整
- 引用完整、格式一致
- 方法论可复现、假设明确
- 结论有据、不过度推断、局限性承认

### generic（通用项目）
- 整体结构清晰、层次导航合理
- 术语和格式一致、内容无重复
- 各部分完整无缺口、工作流可自动化环节
- 关键决策有文档记录

---

## init.py 使用

```bash
# 接管已有项目（任何类型）
python init.py adopt /path/to/project

# 从零初始化新项目（会询问项目类型）
python init.py onboard /path/to/project

# 查看项目就绪状态
python init.py status /path/to/project
```

---

## 升级注意事项

- `config.md` 中 `verification_command` 替代了旧的 pytest 绑定
- `publish_command` 替代了旧的 GitHub Release 字段
- `project_kind` 字段替代了旧的隐式 Python-only 假设
- `bootstrap.py` 已降级为 legacy，仅用于旧项目兼容
