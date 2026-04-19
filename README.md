# Autonomous Improvement Loop

**One agent. One project. Cron-driven autonomous improvement queue.**

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
- All improvement tasks go through an AI-prioritized queue (HEARTBEAT.md)
- Every completed task → commit → optional verification → report
- Queue stays full automatically — the scanner keeps finding new tasks
- The agent never loses context — it remembers the queue across sessions

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
| `a-add <content>` | Add a user requirement to the queue |
| `a-scan` | Rescan the project, refresh the queue (non-user tasks only) |
| `a-clear` | Clear all non-user tasks from the queue |
| `a-queue [--all]` | Show current queue (use `--all` to include done items) |
| `a-log [-n N]` | Show recent Done Log entries (default: 10) |
| `a-refresh [--min N]` | Full queue refresh: clear non-user + scan new items |
| `a-trigger [--force]` | Run cron immediately (skip `cron_lock` check with `--force`) |
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
| `a-scan` | Trigger a queue scan via project_insights.py |
| `a-clear` | Clear non-user tasks from the queue |
| `a-queue` | Show current queue (`--all` to include done items) |
| `a-log` | Show recent Done Log entries (`-n N` for count) |
| `a-refresh` | Full refresh: clear non-user + scan new items |
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
project_insights.py — auto-detect project type, generate improvement ideas
    │  includes "inspire" bucket with type-specific creative questions
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
    │
    ▼
Re-scan queue every run (preserve user tasks, rebuild non-user queue)
```

---

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
| 1 | improve | 72 | [[Improve]] Add unit tests | Full reasoning here... | scanner | done | 2026-04-18 |
```

- **Type**: `improve` | `feature` | `fix` | `wizard` | `user`
- **Score**: 1–100 (higher = more urgent; user requests = 100)
- **Source**: `scanner` | `user` | `agent`
- **Status**: `pending` | `done` | `skip`
- **Content**: ≤30-character summary for cron reporting
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
| `project_insights.py` | Scan project, generate type-specific improvement candidates |
| `priority_scorer.py` | Score queue entries (supports user request insertion) |
| `verify_and_revert.py` | Run verification, rollback on failure |
| `run_status.py` | Read/write Run Status section |
| `update_heartbeat.py` | Post-task updater: HEARTBEAT + queue refresh + inspire scan + PROJECT.md rebuild |
| `inspire_scanner.py` | Generates alternating [[Idea]]/[[Improve]] tasks from project analysis |
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
