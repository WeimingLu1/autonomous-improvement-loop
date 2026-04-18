# File Templates

## config.md

```markdown
# Autonomous Improvement Loop — 项目配置

> 安装 skill 后填写此文件，即完成项目绑定。
> 所有脚本从此文件读取项目路径、仓库、版本文件等配置。

## 项目路径
project_path: ~/Projects/YOUR_PROJECT

## GitHub 仓库
repo: https://github.com/OWNER/REPO

## 版本文件
version_file: ~/Projects/YOUR_PROJECT/VERSION

## 项目内文档目录
docs_agent_dir: ~/Projects/YOUR_PROJECT/docs/agent

## CLI 名称
cli_name: your-cli-name

## OpenClaw Agent ID
agent_id: your-agent-id

## Telegram Chat ID
chat_id: YOUR_TELEGRAM_CHAT_ID

## Cron 调度
cron_schedule: "*/30 * * * *"
cron_timeout: 3600
```

## HEARTBEAT.md

```markdown
# Autonomous Improvement Loop — 队列状态

> Skill: autonomous-improvement-loop | 单 agent × 单项目
> 配置: config.md

---

## Run Status

| 字段 | 值 |
|------|----|
| last_run_time | never |
| last_run_commit | `none` |
| last_run_result | unknown |
| last_run_task | none |
| cron_lock | false |
| rollback_on_fail | true |

---

## Queue

> score 由 priority_scorer 计算，用户请求自动 score=100（插队）
> 排序规则：score 降序，score 相等时按创建时间早的优先

| # | 类型 | score | 内容 | 来源 | 状态 | 创建时间 |
|---|------|-------|------|------|------|----------|

---

## Queue 管理规则

- 用户请求 → score=100 → 立即插队到 #1
- cron 运行时（cron_lock=true）→ 用户请求仍入队，agent 拒绝直接修改文件
- 每次添加条目后，按 score 降序重排序
- cron 执行步骤：① cron_lock=true → ② 执行任务 → ③ commit+push → ④ announce → ⑤ cron_lock=false
```

## DEVLOG.md

```markdown
# Autonomous Improvement Loop — 开发日志

> 此文件记录 skill 对应项目的所有已完成改进，按完成时间倒序排列。
> skill = agent × 项目，1:1 绑定。

---

## YYYY-MM-DD

### ✅ 完成项

| # | 任务 | Commit | Release | 备注 |
|---|------|--------|---------|------|

---

*正在记录中...*
```

## Cron Job Setup

```bash
openclaw cron add \
  --name "Project Improvement Loop" \
  --every 30m \
  --session isolated \
  --agent YOUR_AGENT_ID \
  --model YOUR_MODEL \
  --announce \
  --channel telegram \
  --to YOUR_TELEGRAM_CHAT_ID \
  --timeout-seconds 3600 \
  --message "Autonomous improvement loop triggered"
```
