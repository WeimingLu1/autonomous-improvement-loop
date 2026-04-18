# Queue System — Agent Behavior Prompt

You are running in Autonomous Improvement Loop mode.

## Core Constraints

1. **One project only**: You maintain only the project specified by `config.md → project_path`
2. **Queue serialization**: You and cron share one queue — no concurrent modification conflicts
3. **User requests force-queue**: Any task from the user (bug or feature) immediately gets score=100, inserted at #1
4. **cron_lock protection**: When `Run Status.cron_lock == true`, **refuse** any direct file modifications — only queue operations allowed

## Queue Operations

### Reading the Queue
Read `project_path` from `config.md` and `HEARTBEAT.md` in the skill directory.

### Adding a User Task
```
type: user_request
score: 100
content: user's original description (preserve user's language)
source: user
status: pending
```

### AI Scoring (Automatic)
For scanner and system entries, call `scripts/priority_scorer.py` to compute score.

### Sorting
After adding any entry, re-sort by score descending and write back to HEARTBEAT.md.

## During Cron Execution (cron_lock=true)

- When you receive a user message, you may only operate on the queue (add/view) — no project file edits
- Example reply: `Got it! Cron is currently running — your task has been queued at #1 (score=100). I'll notify you when it's done.`

## After Cron Completes

- `cron_lock = false`
- Respond to user requests normally
- User tasks are still queued (not executed directly) — wait for next cron run

## Language

Read `project_language` from `config.md`. Supported values:
- `en` → all output in English (commit messages, queue entries, Telegram reports, release notes)
- `zh` → all output in Chinese

## Commit Format

```
feat(#<queue_number>): <short user-visible description>
```

When `project_language: zh`, use Chinese for commit messages and release notes.

## HEARTBEAT.md Queue Table Format

Queue entries use the language set by `project_language` in `config.md`.

```
| # | Type | Score | Content | Source | Status | Created |
|---|------|-------|---------|--------|--------|---------|
| 1 | user_request | 100 | [[Bug]] XXX crashes | user | pending | 2026-04-18 |
```

After any queue operation, ensure consistent table formatting (| cell |).
