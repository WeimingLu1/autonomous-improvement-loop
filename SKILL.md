---
name: autonomous-improvement-loop
description: Universal AI PM loop for any project. Maintains ROADMAP.md with one current task, full plans in plans/TASK-xxx.md, PM-generated next-task planning, user-priority task insertion, roadmap-driven execution, and 11 core commands plus aliases. Works for software, writing, video, research, and generic projects. Install: clawhub install autonomous-improvement-loop
---

# Autonomous Improvement Loop — Skill Reference

## Overview

This skill drives a **Universal AI PM Loop** for any long-running project:
**Plan current task → Execute → Verify → Record → Pick next task → Repeat**

Type-agnostic: works for software, writing, video, research, or generic projects.

---

## Core Concepts

### Project Types

The skill auto-detects your project type heuristically during setup. You can also set `project_kind` in `config.md`:

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
│  Cron fires / manual │
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ Read ROADMAP.md     │
│ current task + plan │
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ Execute current task│
│ from plans/TASK-xxx │
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ Record Done Log     │
│ and promote next    │
└─────────┬───────────┘
          ▼
┌─────────────────────┐
│ PM planner chooses  │
│ next concrete task  │
└─────────────────────┘
```

---

## ROADMAP.md Structure

```
## Current Task     ← exactly one current task
## Rhythm State     ← next_default_type + counters + plan path
## PM Notes         ← lightweight operator notes
## Done Log         ← completed tasks
```

### Current Task Fields

| Field | Description |
|-------|-------------|
| `task_id` | `TASK-001` style stable id |
| `type` | `idea` or `improve` |
| `source` | `pm` or `user` |
| `title` | human-readable task title |
| `status` | `pending` \| `doing` \| `done` |
| `created` | creation date |

### Rhythm State Fields

| Field | Description |
|-------|-------------|
| `next_default_type` | next PM-generated task type |
| `improves_since_last_idea` | 2:1 idea/improve rhythm counter |
| `current_plan_path` | active `plans/TASK-xxx.md` path |
| `reserved_user_task_id` | queued user task when a doing task must not be interrupted |

---

## Scripts

| Script | Role | Interface |
|--------|------|----------|
| `init.py` | Setup + roadmap / PM commands | CLI |
| `project_md.py` | Generate PROJECT.md from current project tree | `--project`, `--output`, `--language`, `--repo` |
| `roadmap.py` | ROADMAP.md data model + parsing/writing | module |
| `task_ids.py` | Stable `TASK-xxx` id allocation | module |
| `plan_writer.py` | Write full `plans/TASK-xxx.md` docs | module |
| `task_planner.py` | PM planner for next default task | module |

---

## Verification

`verify_and_revert.py` reads `verification_command` from `config.md`:

- **Empty** → mark task `unverified`, no rollback
- **Configured** → run it; on non-zero exit → auto-revert last commit

Any shell command works. The skill is language-agnostic.

---

## User Request Insertion

Users insert tasks via `a-add` → written as full `plans/TASK-xxx.md` docs with `source=user`. User tasks take priority over PM-generated tasks, but do not interrupt a task already marked `doing`.

---

## Scripts Reference

```
# Generate next PM task
python init.py a-plan

# Show current task + full plan
python init.py a-current

# Add user task
python init.py a-add "Implement dark mode support"

# Execute current task
python init.py a-trigger --force

# Setup
python init.py a-adopt ~/Projects/MY_PROJECT
python init.py a-onboard ~/Projects/MyProject
python init.py a-status ~/Projects/MY_PROJECT
```

## Command System

The skill is invoked via OpenClaw's skill router. Incoming message text is parsed by the leading `a-` prefix:

| Command | Action |
|---------|--------|
| `a-adopt <path>` | Take over an existing project (auto-detect + configure + start) |
| `a-onboard <path>` | Bootstrap a brand-new project from scratch |
| `a-status [path]` | Check project readiness |
| `a-start` | Start cron hosting (create the cron job) |
| `a-stop` | Stop cron hosting (remove the cron job) |
| `a-add <content>` | Create a user-sourced `TASK-xxx` + full plan doc |
| `a-current` | Show current task + full plan doc |
| `a-queue` | Alias to `a-current` |
| `a-log [-n N]` | Show recent roadmap Done Log entries |
| `a-plan [--force]` | Generate the next PM task + full plan doc |
| `a-refresh` | Alias to `a-plan` |
| `a-trigger [--force]` | Execute current roadmap task and record Done Log |
| `a-config get <key>` | Read a config value |
| `a-config set <key> <value>` | Write a config value |

When a user sends a message, the skill parses the first `a-` prefix command; the remaining text is treated as arguments.
