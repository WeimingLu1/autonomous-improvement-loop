# Autonomous Improvement Loop

**One agent. One project. Cron-driven autonomous improvement queue.**

[![ClawHub](https://img.shields.io/badge/Install-ClawHub-6B57FF?style=flat-square)](https://clawhub.ai)
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
python scripts/init.py adopt ~/Projects/MY_PROJECT

# Bootstrap a brand-new project (prompts for project type)
python scripts/init.py onboard ~/Projects/MyProject

# Check project readiness and queue
python scripts/init.py status ~/Projects/MY_PROJECT
```

| Subcommand | Use case |
|-----------|----------|
| `adopt` | Take over an existing project, preserve existing queue, create cron |
| `onboard` | Bootstrap a new project with type-appropriate directory structure |
| `status` | Show readiness checklist, queue contents, cron status |

### 3. Cron starts automatically

After `adopt` or `onboard`, the cron job runs every 30 minutes automatically.

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
Queue refreshed if below minimum
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
| # | Type | Score | Content | Source | Status | Created |
|---|------|-------|---------|--------|--------|---------|
| 1 | improve | 72 | [[Improve]] Add unit tests for untested module | scanner | done | 2026-04-18 |
```

- **Type**: `improve` | `feature` | `fix` | `wizard` | `user`
- **Score**: 1–100 (higher = more urgent; user requests = 100)
- **Source**: `scanner` | `user` | `agent`
- **Status**: `pending` | `done` | `skip`

---

## Scripts

| Script | Purpose |
|--------|---------|
| `init.py` | adopt / onboard / status — main setup tool |
| `project_insights.py` | Scan project, generate type-specific improvement candidates |
| `priority_scorer.py` | Score queue entries (supports user request insertion) |
| `verify_and_revert.py` | Run verification, rollback on failure |
| `run_status.py` | Read/write Run Status section |
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
