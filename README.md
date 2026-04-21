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
| `a-scan` | Legacy scan command |
| `a-clear` | Legacy cleanup command |
| `a-current` | Show current task and full plan doc |
| `a-queue [--all]` | Alias to `a-current` |
| `a-log [-n N]` | Show recent roadmap Done Log entries |
| `a-plan [--force]` | Generate the next PM task and full plan doc |
| `a-refresh [--min N]` | Alias to `a-plan` |
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

# Check project readiness and queue
python scripts/init.py a-status ~/Projects/MY_PROJECT
```

| Subcommand | Use case |
|-----------|----------|
| `a-adopt` | Take over an existing project, preserve existing queue, create cron |
| `a-onboard` | Bootstrap a new project with type-appropriate directory structure |
| `a-status` | Show readiness checklist, queue contents, cron status |
| `a-start` | Start cron hosting (create cron job from config.md) |
| `a-stop` | Stop cron hosting (remove cron job) |
| `a-add` | Add a user requirement to the queue |
| `a-scan` | **Legacy** — trigger a queue scan via `project_insights.py`; prefer `a-refresh` |
| `a-clear` | Clear non-user tasks from the queue |
| `a-queue` | Show current queue (`--all` to include done items) |
| `a-log` | Show recent Done Log entries (`-n N` for count) |
| `a-refresh` | Rebuild rolling queue from latest project state |
| `a-trigger` | Run cron immediately (`--force` to skip cron_lock) |
| `a-config` | Read/write config values (`get`/`set`) |

### 3. Cron starts automatically

After `adopt` or `start`, the cron job runs every 30 minutes automatically.

---

## How It Works

```
Cron fires (every 30 min)
    │
    ▼
Acquire cron_lock — prevent concurrent runs
    │
    ▼
inspire_scanner.py — rebuild rolling 6-item backlog in one shot
    │  Alternating 2:1 cycle: idea → improve → improve → idea → improve → improve
    │  Deduplicates against: existing queue + Done Log + last generated content
    │  Improve tasks target the most-active git module; Ideas come from inspire questions
    │
    ▼
Pick top task from queue (highest score, not yet done)
    │
    ▼
Agent implements the task → git commit
    │
    ▼
verify_and_revert.py — run verification_command from config.md
  • pass       → mark done, push
  • fail       → auto-revert commit, push
  • unverified → mark unverified, notify (no verification_command set)
    │
    ▼
Telegram report + update HEARTBEAT.md
    │  (rolling queue rebuild + PROJECT.md rebuild happen on next cron tick)
    │
    ▼
Release cron_lock
```

---

## Alternating Queue System

The queue is rebuilt on every run into a rolling backlog, while still following a fixed 2:1 rhythm:

| Cycle | Generates | `improves_since_last_idea` counter |
|-------|-----------|-------------------------------------|
| 1st | `[[Idea]]` (new capability or UX innovation) | reset to 0 |
| 2nd | `[[Improve]]` (targeted improvement) | increment → 1 |
| 3rd | `[[Improve]]` (second in streak) | increment → 2 |
| 4th | `[[Idea]]` (flip back to innovation) | reset to 0 |

The rolling backlog always maintains **6 pending tasks** in this alternating order:

`idea → improve → improve → idea → improve → improve`

On every run `inspire_scanner.py` rebuilds the entire non-user portion of the queue from scratch, using the latest project state (recent git activity for Improves, inspire questions for Ideas). User tasks are always preserved.

**Why this ratio?** Ideas (score 65) naturally outrank Improves (score 45) when both appear, so a 2:1 ratio keeps the queue balanced without hardcoding type preferences in the sort key.

### Alternation Triggers

- Reads `[[Idea]]` / `[[Improve]]` tags from the **Done Log** to detect last committed task type
- Stores `improves_since_last_idea` counter in the **Run Status** table
- On every run, `inspire_scanner.py` generates the next `target_size` items in alternation order starting from the current Done Log state
- Deduplication covers: Queue (pending) + Done Log (completed, including items with execution notes appended) + last generated content
  - **Prefix dedup**: if a Done Log entry starts with the queue item text (agent appended execution notes in parentheses), they are considered the same task and skipped

### Idea vs Improve Quality

- **[[Idea]]**: from `PROJECT.md` inspire questions — new capability, UX innovation, workflow improvement, or competitive benchmarking
- **[[Improve]]**: git-activity-informed — targets the most-changed module since last idea; falls back to generic improvement if no recent commits

### Inspire Questions

Open-ended questions in `PROJECT.md` seed [[Idea]] generation. Examples per project type:

| Type | Inspire questions |
|------|-------------------|
| `software` | What CLI patterns could reduce friction? What would make tests easier to write? |
| `writing` | What pacing issues does this chapter have? Which character needs more depth? |
| `video` | What scenes feel slow? Where could the narrative be tighter? |
| `research` | What methodology gaps exist? What counter-arguments are missing? |

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
project_language:      # optional: zh = Chinese queue output, en = English, empty = follow agent preference

verification_command:   # empty = no auto-verification
publish_command:        # optional: runs after successful task

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

## Queue Format (HEARTBEAT.md)

```
| # | Type | Score | Content | Detail | Source | Status | Created |
|---|------|-------|---------|--------|--------|--------|---------|
| 1 | idea | 65 | [[Idea]] Add interactive mode | Full reasoning here... | inspire: CLI | pending | 2026-04-19 |
| 2 | improve | 45 | [[Improve]] Add unit tests | Full reasoning here... | git: src/cli/ | pending | 2026-04-19 |
```

- **Type**: `idea` (innovation) | `improve` (targeted improvement) | `feature` | `fix` | `wizard` | `user`
- **Score**: 1–100 (higher = more urgent; user requests = 100; ideas score 65, improves score 45)
- **Source**: `inspire: <question>` (idea from inspire question) | `git: <module>` (improve targeting most-active module) | `scanner` | `user` | `agent`
- **Status**: `pending` | `done` | `skip`
- **Content**: ≤30-character summary for cron reporting; prefixed with `[[Idea]]` or `[[Improve]]` tag
- **Detail**: Full original intent / analysis rationale; user requests recorded verbatim, AI-generated tasks include complete reasoning

---

## PROJECT.md — Project Description

The skill maintains a `PROJECT.md` file at the skill root. It stores a type-aware description of the managed project, including:

- Basic info (type, tech stack, repo, version)
- Project positioning
- Core features
- Technical architecture
- Recent activity log
- Open-ended inspiration questions (type-specific)

The project description (type, positioning, features, architecture, inspire questions) is captured at adopt/onboard time. It serves as the agent's long-term context for the project — what it is and where it could go — separate from the execution log in HEARTBEAT.md.

---

## Scripts

| Script | Purpose |
|--------|---------|
| `init.py` | a-adopt / a-onboard / a-status / a-start / a-stop / a-add / a-scan / a-clear / a-queue / a-log / a-refresh / a-trigger / a-config |
| `project_insights.py` | Used internally by inspire_scanner for git-activity-based Improve generation |
| `priority_scorer.py` | Score queue entries (supports user request insertion) |
| `verify_and_revert.py` | Run verification, rollback on failure |
| `run_status.py` | Read/write Run Status section |
| `update_heartbeat.py` | Post-task updater: mark done + append to Done Log + rebuild rolling queue (inspire_scanner) + rebuild PROJECT.md |
| `inspire_scanner.py` | Rebuilds rolling 6-item backlog in alternating 2:1 order (idea→improve→improve→idea→improve→improve); deduplicates against queue + Done Log + last generated content; Improve tasks target most-active git module |
| `project_md.py` | Generate PROJECT.md from current project tree (used by adopt / onboard / every task) |
| `bootstrap.py` | Legacy helper for old Python software projects |
| `queue_scanner.py` | **Legacy** — redirects to `project_insights.py` |
| `rollback_if_unstable.py` | **Legacy** — redirects to `verify_and_revert.py` |
| `verify_cli_docs.py` | Check CLI docs are in sync with --help output |

---

## Migrating from v4 / v5

- `queue_scanner.py` → replaced by `project_insights.py` (same CLI interface, generic buckets)
- `rollback_if_unstable.py` → replaced by `verify_and_revert.py` (reads `verification_command` from config)
- `config.md` fields `version_file`, `cli_name`, `docs_dir` → removed (no longer required)
- `config.md` new fields: `project_kind`, `verification_command`, `publish_command`
- `project_language` replaces per-command `--zh` flags
- Queue format now includes `Detail` field for full intent capture
- Command system (`a-start`, `a-stop`, `a-add`, `a-scan`, `a-clear`) added via skill router
- Cron runs now explicitly refresh the non-user queue after every completed task
- `PROJECT.md` added for type-aware project description
