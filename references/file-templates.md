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

- **User request** → score=100 → immediately inserted at #1, all others shift down
- **cron_lock=true** during execution: skip queue edits, agent refuses direct file edits
- **After adding**: re-sort by score descending, write back to HEARTBEAT.md
- **Cron sequence**: cron_lock → execute → verify/publish → announce → cron_unlock
```

## config.md Template

```yaml
project_path: .
project_kind: generic   # software | writing | video | research | generic
repo: https://github.com/OWNER/REPO
agent_id: YOUR_AGENT_ID
chat_id: YOUR_TELEGRAM_CHAT_ID
project_language:      # optional: zh = Chinese, en = English, empty = follow agent preference
verification_command:
publish_command:
cron_schedule: "*/30 * * * *"
cron_timeout: 3600
cron_job_id:
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

**Language resolution for project content:**
1. explicit `--language` argument
2. configured `project_language` in config.md
3. agent language preference
4. project content detection
5. English fallback

The skill UI (SKILL.md, README.md, scripts, reports) is always in English.
The managed project's queue content and task descriptions follow `project_language`.

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
