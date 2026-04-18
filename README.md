# Autonomous Improvement Loop

**One agent. One project. Cron-driven autonomous improvement queue.**

[![ClawHub](https://img.shields.io/badge/Install-ClawHub-6B57FF?style=flat-square)](https://clawhub.ai/weiminglu1/autonomous-improvement-loop)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

---

## What Is This?

A skill for [OpenClaw](https://github.com/openclaw/openclaw) agents that turns your agent into a **self-sustaining improvement machine** for a single project.

**Type-agnostic** — works for any long-running project:

- **Software** — code, CLI tools, libraries
- **Writing** — novels, scripts, blog posts
- **Video** — scripts, storyboards, footage projects
- **Research** — papers, theses, literature reviews
- **Generic** — any structured long-term work

Once installed and configured:

- Your agent continuously improves your project on a schedule (cron-driven)
- All improvement tasks go through an AI-prioritized queue (HEARTBEAT.md)
- Every completed task → commit → optional publish → report
- Queue stays full automatically — the scanner keeps finding new tasks
- The agent never loses context — it remembers the queue across sessions

---

## Project Types

The skill auto-detects your project type and generates relevant improvement ideas.

| Type | Indicators | Example improvements |
|------|-----------|---------------------|
| `software` | `src/`, `tests/`, `Cargo.toml` | test coverage, docs, CLI UX |
| `writing` | `chapters/`, `outline.md` | plot consistency, pacing, character voice |
| `video` | `scripts/`, `scenes/`, `storyboard/` | scene pacing, shot clarity, continuity |
| `research` | `papers/`, `references/`, `*.tex` | citation gaps, structure, methodology |
| `generic` | any directory | structure, clarity, consistency |

---

## Quick Start

### 1. Install

```bash
clawhub install autonomous-improvement-loop
```

### 2. One-command setup

```bash
# 接管已有项目（任何类型）
python scripts/init.py adopt ~/Projects/YOUR_PROJECT

# 从零初始化新项目（会询问项目类型）
python scripts/init.py onboard ~/Projects/MyProject

# 查看项目状态
python scripts/init.py status ~/Projects/YOUR_PROJECT
```

| Subcommand | Use case |
|------------|----------|
| `adopt` | Take over an existing project, preserve queue, create cron |
| `onboard` | Bootstrap a brand-new project, set up directory structure |
| `status` | Show readiness, queue contents, cron status |

### 3. Cron starts automatically

After `adopt` or `onboard`, the cron job runs every 30 minutes automatically.

---

## How It Works

```
Cron fires (every 30 min)
    │
    ▼
Acquire cron_lock (prevent concurrent runs)
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
  - pass    → mark done, push
  - fail    → auto-revert commit, push
  - unverified (no command configured) → mark unverified, notify
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

- **Empty** → no auto-verification, task marked `unverified`
- **Configured** → runs the command; on failure, auto-reverts the last commit

Examples:

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
project_kind: generic      # software | writing | video | research | generic
                          # leave empty for auto-detection
project_language: zh      # zh = Chinese, en = English
github_repo: https://github.com/OWNER/REPO

verification_command:       # empty = no auto-verification
publish_command:          # optional: runs after successful task

cron_schedule: "*/30 * * * *"
cron_enabled: true
```

---

## Queue Format (HEARTBEAT.md)

```
| # | Type | Score | Content | Source | Status | Created |
|---|------|-------|---------|--------|--------|---------|
| 1 | improve | 72 | [[Improve]] 为未测试的模块补齐单元测试 | scanner | done | 2026-04-18 |
```

- **Type**: `improve` | `feature` | `fix` | `wizard` | `user`
- **Score**: 1–100 (higher = more urgent)
- **Source**: `scanner` | `user` | `agent`
- **Status**: `pending` | `done` | `skip`

---

## Scripts

| Script | Purpose |
|--------|---------|
| `init.py` | adopt / onboard / status — the main setup tool |
| `project_insights.py` | Scan project, generate improvement candidates |
| `priority_scorer.py` | Score queue entries (supports user requests) |
| `verify_and_revert.py` | Run verification, rollback on failure |
| `run_status.py` | Read/write Run Status section |
| `bootstrap.py` | Legacy helper for Python software projects |

---

## Migrating from v4 / v5

- `queue_scanner.py` → renamed to `project_insights.py` (same interface, generic buckets)
- `rollback_if_unstable.py` → renamed to `verify_and_revert.py` (reads `verification_command` from config)
- `config.md` fields `version_file`, `cli_name`, `docs_dir` → removed (no longer required)
- `config.md` new fields: `project_kind`, `verification_command`, `publish_command`
- `project_language` replaces per-command `--zh` flags
