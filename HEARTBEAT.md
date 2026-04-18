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
| 1 | improve | 65 | [[Improve]] 审查情节一致性：检查时间线矛盾 | scanner | pending | 2026-04-18 |
| 2 | improve | 65 | [[Improve]] 找出并解决早期章节遗留的未解情节线索 | scanner | pending | 2026-04-18 |
| 3 | improve | 60 | [[Improve]] 强化核心冲突：是否能撑过中段？ | scanner | pending | 2026-04-18 |
| 4 | improve | 60 | [[Improve]] 审查章节钩子：每个章节结尾是否有悬念？ | scanner | pending | 2026-04-18 |
| 5 | improve | 65 | [[Improve]] 审查角色声音一致性：每个角色是否有独特语言风格？ | scanner | pending | 2026-04-18 |

---

## Queue Management Rules

- **User request** → score=100 → immediately inserted at #1, all others shift down
- **During cron execution** (cron_lock=true): user requests can still join queue, agent refuses direct file edits
- **After adding any entry**: re-sort by score descending, write back to HEARTBEAT.md
- **Cron execution sequence**: ① cron_lock=true → ② execute task → ③ verify/publish if configured → ④ announce → ⑤ cron_lock=false
