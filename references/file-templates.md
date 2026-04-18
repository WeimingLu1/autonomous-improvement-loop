# Reference: File Templates

## HEARTBEAT.md Template

```markdown
# Autonomous Improvement Loop — Queue Status

> Skill: autonomous-improvement-loop | One agent x One project
> Config: config.md

---

## Run Status

| Field | Value |
|-------|-------|
| last_run_time | — |
| last_run_commit | — |
| last_run_result | unknown |
| last_run_task | — |
| cron_lock | false |
| mode | bootstrap |
| rollback_on_fail | true |

---

## Queue

| # | Type | Score | Content | Source | Status | Created |
|---|------|-------|---------|--------|--------|---------|

---

## Queue Management Rules

- **User request** → score=100 → immediately inserted at #1
- **cron_lock=true** during execution: skip queue edits
- **After adding**: re-sort by score descending
- **Cron sequence**: cron_lock → execute → verify/publish → announce → cron_unlock
```

## config.md Template

```yaml
project_path: .
project_kind:           # software | writing | video | research | generic
project_language: en   # zh = Chinese, en = English
github_repo: https://github.com/OWNER/REPO
verification_command:
publish_command:
cron_schedule: "*/30 * * * *"
cron_enabled: true
```

## Telegram Report Template (English)

```markdown
📋 Improvement Report — {project_name}

Completed: {done_count} task(s)
Duration: {duration}
Result: {result}

{if failures}:
⚠️ Failed:
{list}
{/if}

{if unverified}:
⚠️ Unverified — manual check required
{/if}

Next: {next_task}
Round: {iteration}
```

## Telegram Report Template (Chinese)

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

## Cron Creation (openclaw CLI)

```bash
openclaw cron add \
  --name "Autonomous Improvement Loop" \
  --every 30m \
  --session isolated \
  --agent YOUR_AGENT_ID \
  --timeout-seconds 3600 \
  --announce \
  --channel telegram \
  --to YOUR_CHAT_ID
```
