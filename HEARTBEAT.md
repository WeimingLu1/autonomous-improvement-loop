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

## Done Log

| Time | Commit | Task | Result |
|------|--------|------|--------|

## Queue Management Rules

- **User request** → score=100 → immediately inserted at #1, all others shift down
- **During cron execution** (`cron_lock=true`): user requests can still join queue, agent refuses direct file edits
- **After adding any entry**: re-sort by score descending, write back to HEARTBEAT.md
- **Cron execution sequence**: ① `cron_lock=true` → ② execute task → ③ verify/publish if configured → ④ announce → ⑤ `cron_lock=false`
