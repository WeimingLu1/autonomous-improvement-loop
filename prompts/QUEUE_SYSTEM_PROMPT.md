# Queue System Prompt

> Queue management rules for the Autonomous Improvement Loop skill.

## Queue Format

```
| # | Type | Score | Content | Source | Status | Created |
|---|------|-------|---------|--------|--------|---------|
```

## Queue Management Rules

- **User request** → score=100 → immediately inserted at #1, all others shift down
- **During cron execution** (cron_lock=true): user requests can still join queue, agent refuses direct file edits
- **After adding any entry**: re-sort by score descending, write back to HEARTBEAT.md
- **Cron execution sequence**: ① cron_lock=true → ② execute task → ③ verify/publish if configured → ④ announce → ⑤ cron_lock=false

## Scoring

- Score 1–100 (higher = more urgent)
- User requests auto → score=100 (forced to top)
- Scanner entries: configurable, typically 45–72

## Type Values

- `improve` — incremental improvement (refactor, UX, docs)
- `feature` — new feature
- `fix` — bug fix
- `wizard` — guided setup / interactive task
- `user` — user-requested task

## Status Values

- `pending` — queued, not yet executed
- `done` — completed and verified
- `skip` — intentionally skipped

## Language

The queue output language is controlled by `project_language` in `config.md`:
- `en` → English entries
- `zh` → Chinese entries

The scanner generates bilingual ideas (both EN+ZH) when `project_language` is set accordingly.
