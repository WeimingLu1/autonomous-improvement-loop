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

> Scores from priority_scorer; user requests auto score=100 (forced to #1)
> Sort: score descending, ties broken by creation time (older first)

| # | Type | Score | Content | Source | Status | Created |
|---|------|-------|---------|--------|--------|---------|
| 1 | feature | 65 | [[Feature]] Your first feature here | user | pending | 2026-04-18 |
| 2 | improve | 50 | [[Improve]] Add unit tests for core module | system | pending | 2026-04-18 |

---

## Queue Management Rules

- **User request** → score=100 → immediately inserted at #1, all others shift down
- **During cron execution** (cron_lock=true): user requests can still join queue, agent refuses direct file edits
- **After adding any entry**: re-sort by score descending, write back to HEARTBEAT.md
- **Cron execution sequence**: ① cron_lock=true → ② execute task → ③ commit+push → ④ announce → ⑤ cron_lock=false
- **mode switch**: when project passes readiness check, mode auto-switches from `bootstrap` to `normal`
