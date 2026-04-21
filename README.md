# Autonomous Improvement Loop

**One agent. One project. Cron-driven AI PM loop.**

[![ClawHub](https://img.shields.io/badge/Install-ClawHub-6B57FF?style=flat-square)](https://clawhub.ai/skills/autonomous-improvement-loop)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

---

## What Is This?

A skill for [OpenClaw](https://github.com/openclaw/openclaw) agents that turns your agent into a **self-sustaining improvement machine** for a single project.

**Type-agnostic** — works for any long-running project:

| Type | Description | Example improvements |
|------|-------------|---------------------|
| `software` | Code projects | test coverage, docs, CLI UX |
| `writing` | Prose / scripts | plot consistency, pacing, character voice |
| `video` | Media / footage | scene pacing, shot clarity, continuity |
| `research` | Papers / theses | citation gaps, structure, methodology |
| `generic` | Any structured work | structure, clarity, consistency |

Once installed and configured:

- Your agent continuously improves your project on a schedule (cron-driven)
- All work flows through `ROADMAP.md` plus full plans in `plans/TASK-xxx.md`
- Every completed task is recorded in roadmap Done Log
- PM planner keeps choosing the next concrete task
- The agent never loses context across sessions

---

## Command System

After installation, interact with the loop via these commands:

| Command | Action |
|---------|--------|
| `a-adopt <path>` | Take over an existing project (auto-detect + configure + start) |
| `a-onboard <path>` | Bootstrap a brand-new project from scratch |
| `a-status [path]` | Check project readiness |
| `a-start` | Start cron hosting (create the cron job) |
| `a-stop` | Stop cron hosting (remove the cron job) |
| `a-add <content>` | Create a user-sourced `TASK-xxx` plan |
| `a-current` | Show current task and full plan doc |
| `a-queue` | Alias to `a-current` |
| `a-log [-n N]` | Show recent roadmap Done Log entries |
| `a-plan [--force]` | Generate the next PM task and full plan doc |
| `a-refresh` | Alias to `a-plan` |
| `a-trigger [--force]` | Execute current roadmap task and record Done Log |
| `a-config get <key>` | Read a config value |
| `a-config set <key> <value>` | Write a config value |

Commands are routed through OpenClaw's skill system — send them as messages and the skill parses the leading `a-` prefix automatically.

---

## Project Type Auto-Detection

The skill auto-detects your project type and generates relevant improvement ideas. You can also set `project_kind` manually in `config.md`.

---

## Quick Start

### 1. Install

```bash
clawhub install autonomous-improvement-loop
```

### 2. One-command setup

```bash
# Take over an existing project (any type)
python scripts/init.py a-adopt ~/Projects/MY_PROJECT

# Bootstrap a brand-new project (prompts for project type)
python scripts/init.py a-onboard ~/Projects/MyProject

# Check project readiness
python scripts/init.py a-status ~/Projects/MY_PROJECT
```

| Subcommand | Use case |
|-----------|----------|
| `a-adopt` | Take over an existing project and create cron |
| `a-onboard` | Bootstrap a new project with type-appropriate directory structure |
| `a-status` | Show readiness checklist, roadmap status, cron status |
| `a-start` | Start cron hosting (create cron job from config.md) |
| `a-stop` | Stop cron hosting (remove cron job) |
| `a-add` | Create a user-sourced `TASK-xxx` plan |
| `a-current` | Show current task and full plan doc |
| `a-queue` | Alias to `a-current` |
| `a-log` | Show recent roadmap Done Log entries (`-n N` for count) |
| `a-plan` | Generate next PM task and full plan doc |
| `a-refresh` | Alias to `a-plan` |
| `a-trigger` | Execute current roadmap task and record Done Log |
| `a-config` | Read/write config values (`get`/`set`) |

### 3. Cron starts automatically

After `adopt` or `start`, the cron job runs every 30 minutes automatically.

---

## How It Works

```
Cron fires (every 30 min) or you run a-trigger
    │
    ▼
Read ROADMAP.md current task
    │
    ▼
Open plans/TASK-xxx.md full plan
    │
    ▼
Agent executes the current task
    │
    ▼
Run verification_command from config.md (optional)
    │
    ▼
Append Done Log entry in ROADMAP.md
    │
    ▼
Promote reserved user task or generate next PM task
```

---

## Task Rhythm

PM-generated tasks follow a simple default rhythm:

`idea → improve → improve → idea → improve → improve`

This rhythm is stored in `ROADMAP.md` via:

- `next_default_type`
- `improves_since_last_idea`
- `current_plan_path`
- `reserved_user_task_id`

### User task priority

User tasks created through `a-add` take priority over PM-generated tasks, but they do **not** interrupt a task already marked `doing`.

## Verification & Rollback

The skill reads `verification_command` from `config.md`.

- **Empty** → no auto-verification; task is marked `unverified`
- **Configured** → runs the command; on failure, auto-reverts the last commit

```yaml
# Software: run test suite
verification_command: pytest tests/ -q

# Writing: spell-check
verification_command: python -m spellchecker .

# Video: duration check
verification_command: ffprobe -v error -show_entries format=duration -i footage.mov

# Research: structure check
verification_command: python -m mypaper.check
```

---

## Configuration (config.md)

```yaml
project_path: .
project_kind: generic   # software | writing | video | research | generic
repo: https://github.com/OWNER/REPO
agent_id: YOUR_AGENT_ID
chat_id: YOUR_TELEGRAM_CHAT_ID
project_language:      # optional: zh = Chinese roadmap output, en = English, empty = follow agent preference

verification_command:   # empty = no auto-verification
cron_schedule: "*/30 * * * *"
cron_timeout: 3600
cron_job_id:
```

Language resolution order is:
1. explicit `--language`
2. configured `project_language`
3. agent language preference
4. project content detection
5. English

---

## ROADMAP Format

`ROADMAP.md` stores exactly one current task plus the execution history.

```markdown
## Current Task
| task_id | type | source | title | status | created |
| TASK-001 | idea | pm | Improve CLI onboarding | pending | 2026-04-21 |

## Rhythm State
| field | value |
| next_default_type | improve |
| improves_since_last_idea | 1 |
| current_plan_path | plans/TASK-001.md |
| reserved_user_task_id |  |

## Done Log
| time | task_id | type | source | title | result | commit |
```

Each task also has a full plan doc in `plans/TASK-xxx.md`, including goal, context, scope, execution plan, acceptance criteria, verification, and risks.

---

## PROJECT.md — Project Description

The skill maintains a `PROJECT.md` file at the skill root. It stores a type-aware description of the managed project, including:

- Basic info (type, tech stack, repo, version)
- Project positioning
- Core features
- Technical architecture
- Recent activity log
- Open-ended inspiration questions (type-specific)

The project description (type, positioning, features, architecture, inspire questions) is captured at adopt/onboard time. It serves as the agent's long-term context for the project, separate from the execution log in `ROADMAP.md`.

---

## Scripts

| Script | Purpose |
|--------|---------|
| `init.py` | Main CLI and roadmap-driven PM flow |
| `roadmap.py` | ROADMAP.md parsing and writing |
| `task_ids.py` | Stable `TASK-xxx` id allocation |
| `task_planner.py` | PM planner for next default task |
| `plan_writer.py` | Write full `plans/TASK-xxx.md` docs |
| `project_md.py` | Generate PROJECT.md from current project tree |
| `verify_and_revert.py` | Run verification, rollback on failure |
