---
name: autonomous-improvement-loop
description: Universal continuous improvement loop for any project. Agent-driven queue, cron scheduler, type-aware scanner, command system (a_start/stop/add/scan/clear), Detail field for full intent capture, inspire bucket for creative discovery. Works for software, writing, video, research, and generic projects. Install: clawhub install autonomous-improvement-loop
---

# Autonomous Improvement Loop — Skill Reference

## Overview

This skill drives a **Universal Continuous Improvement Loop** for any long-running project:
**Maintain task queue → Pick highest priority → Execute → Verify → Record → Repeat**

Type-agnostic: works for software, writing, video, research, or generic projects.

---

## Core Concepts

### Project Types

The skill auto-detects your project type via `project_insights.py`. You can also set `project_kind` in `config.md`:

| Type | Indicators | Description |
|------|-----------|-------------|
| `software` | `src/`, `tests/`, `Cargo.toml` | Code / CLI / library projects |
| `writing` | `chapters/`, `outline.md` | Novels, scripts, blog posts |
| `video` | `scripts/`, `scenes/`, `storyboard/` | Film, documentary, footage projects |
| `research` | `papers/`, `references/`, `*.tex` | Academic papers, literature reviews |
| `generic` | any directory | Any structured long-term work |

### Improvement Loop Lifecycle

```
┌─────────────────────┐
│  Cron fires (30 min) │
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ Acquire cron_lock   │  ← prevent concurrent runs
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ project_insights.py │  ← scan project, generate candidates
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ Pick top queue task  │  ← highest score, not done yet
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ Agent executes      │  ← git commit
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ verify_and_revert.py│  ← verify → pass / fail → revert
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ Report + update     │  ← Telegram + HEARTBEAT.md
│ Re-scan queue      │  ← preserve user tasks, refresh non-user queue every run
└─────────────────────┘
```

---

## HEARTBEAT.md Structure

```
## Run Status        ← runtime state
## Queue            ← task queue (working area)
## Done Log         ← completed tasks
---
```

### Run Status Fields

| Field | Description |
|-------|-------------|
| `last_run_time` | ISO timestamp of last run |
| `last_run_commit` | Git hash of last commit |
| `last_run_result` | `pass` \| `fail` \| `unverified` |
| `last_run_task` | Description of last task |
| `cron_lock` | `true` = someone is editing queue, skip this run |
| `mode` | `bootstrap` \| `normal` |
| `rollback_on_fail` | `true` = auto-revert on verification failure |

### Queue Fields

| Field | Description |
|-------|-------------|
| `Type` | `improve` \| `feature` \| `fix` \| `wizard` \| `user` |
| `Score` | 1–100 (higher = more urgent; user requests auto → 100) |
| `Source` | `scanner` \| `user` \| `agent` |
| `Status` | `pending` \| `done` \| `skip` |
| `Content` | ≤30-character summary for cron reporting |
| `Detail` | Full original intent / analysis rationale; user requests recorded verbatim, AI-generated tasks include complete reasoning |

---

## Scripts

| Script | Role | Interface |
|--------|------|----------|
| `init.py` | Setup: adopt / onboard / status | CLI |
| `project_insights.py` | Scan project, generate candidates | `--project`, `--heartbeat`, `--language`, `--refresh`, `--min` |
| `priority_scorer.py` | Score queue entries | stdin/stdout |
| `verify_and_revert.py` | Verify task, rollback on failure | `--project`, `--heartbeat`, `--commit`, `--task` |
| `run_status.py` | Read/write Run Status | `--heartbeat`, `read`/`write` |

---

## Verification

`verify_and_revert.py` reads `verification_command` from `config.md`:

- **Empty** → mark task `unverified`, no rollback
- **Configured** → run it; on non-zero exit → auto-revert last commit

Any shell command works. The skill is language-agnostic.

---

## User Request Insertion

Users insert tasks via message → directly written to HEARTBEAT.md Queue with score=100 (forced to #1).

---

## Scripts Reference

```
# Scan once, append best candidate
python project_insights.py --project . --heartbeat HEARTBEAT.md --language en

# Keep scanning until queue has at least N items
python project_insights.py --project . --heartbeat HEARTBEAT.md --language en --refresh --min 5

# Rebuild non-user queue after a cron task
python init.py clear
python project_insights.py --project . --heartbeat HEARTBEAT.md --language en --refresh --min 5

# Verify and auto-revert on failure
python verify_and_revert.py \
  --project /path/to/project \
  --heartbeat HEARTBEAT.md \
  --commit <git-hash> \
  --task "description of what was done"

# Setup
python init.py adopt ~/Projects/MY_PROJECT
python init.py onboard ~/Projects/MY_PROJECT
python init.py status ~/Projects/MY_PROJECT
```

## Command System

The skill is invoked via OpenClaw's skill router. Incoming message text is parsed by the leading `a-` prefix:

| Command | Action |
|---------|--------|
| `a_start` | Start hosting: create the cron job |
| `a_stop` | Stop hosting: remove the cron job |
| `a_add <content>` | Add a user requirement to the queue |
| `a_scan` | Rescan the project, refresh the queue (non-user tasks only) |
| `a_clear` | Clear all non-user tasks from the queue |

When a user sends a message, the skill parses the first `a-` prefix command; the remaining text is treated as arguments.
