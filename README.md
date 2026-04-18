# Autonomous Improvement Loop

**One agent. One project. Cron-driven autonomous development queue.**

[![ClawHub](https://img.shields.io/badge/Install-ClawHub-6B57FF?style=flat-square)](https://clawhub.ai/weiminglu1/autonomous-improvement-loop)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

---

## What Is This?

A skill for [OpenClaw](https://github.com/openclaw/openclaw) agents that turns your agent into a **self-sustaining development machine** for a single project.

Once installed and configured:

- Your agent continuously improves your project on a schedule (cron-driven)
- All improvement tasks go through an AI-prioritized queue
- Every completed task → `git commit` → `git push` → GitHub Release → Telegram report
- The agent never loses context — it remembers the queue across sessions

## Two Modes

### Normal Loop — For Established Projects

Your agent picks the highest-priority task from the queue, implements it, commits, releases, and reports back. No manual intervention needed.

### Bootstrap Mode — For New Projects

If your project is too new (no VERSION, no tests, empty queue), the agent enters Bootstrap Mode. It tells you exactly what's missing and waits until you're ready — it won't touch your code until the foundation is in place.

## Quick Start

### 1. Install

```
clawhub install autonomous-improvement-loop
```

Or install manually:
```bash
# Clone this repo
git clone https://github.com/WeimingLu1/autonomous-improvement-loop.git
# Point OpenClaw to it (see OpenClaw docs)
```

### 2. Configure

Edit `config.md` in the skill directory:

```markdown
## Project Path
project_path: ~/Projects/YOUR_PROJECT

## GitHub Repository
repo: https://github.com/OWNER/REPO

## Version File
version_file: ~/Projects/YOUR_PROJECT/VERSION

## Telegram Chat ID
chat_id: YOUR_TELEGRAM_CHAT_ID
```

### 3. For Existing Projects — Add Initial Queue

Open `HEARTBEAT.md` and add your known bugs/features:

```markdown
## Queue

| # | Type | Score | Content | Source | Status | Created |
|---|------|-------|---------|--------|--------|---------|
| 1 | feature | 65 | [[Feature]] Add dark mode | user | pending | 2026-04-18 |
```

### 4. For New Projects — Bootstrap First

Your project needs these minimums before Normal Loop activates:

- [ ] `VERSION` file exists (e.g. `0.0.1`)
- [ ] `pytest -q` passes
- [ ] At least one item in the queue

The agent will tell you what's missing during Bootstrap Mode.

### 5. Start Cron

```bash
openclaw cron add \
  --name "Autonomous Improvement Loop" \
  --every 30m \
  --session isolated \
  --agent YOUR_AGENT_ID \
  --model minimax-portal/MiniMax-M2.7 \
  --announce \
  --channel telegram \
  --to YOUR_TELEGRAM_CHAT_ID \
  --timeout-seconds 3600 \
  --message "Autonomous improvement loop triggered"
```

## How It Works

```
Cron fires (every 30 min)
    │
    ▼
Read queue (HEARTBEAT.md)
    │
    ▼
Pick top task by score
    │
    ▼
Implement + pytest
    │
    ▼
git add → commit → push
    │
    ▼
pytest → auto-revert on failure
    │
    ▼
Update docs + VERSION bump
    │
    ▼
GitHub Release + Telegram report
    │
    ▼
Scan for next improvement
    │
    ▼
Wait for next cron
```

## Queue Priority

| Score | Meaning |
|-------|---------|
| 100 | User request (forced to #1) |
| 90-100 | Bug breaking core functionality |
| 70-89 | Bug in non-core feature |
| 65-79 | Important feature enhancement |
| 50-64 | General feature |
| 30-49 | Internal improvement (tests, docs) |

## File Structure

```
autonomous-improvement-loop/
├── SKILL.md               ← Skill definition (for OpenClaw)
├── README.md              ← This file
├── config.md              ← Project binding configuration
├── HEARTBEAT.md           ← Queue + Run Status
├── DEVLOG.md              ← Completed tasks archive
├── LICENSE
└── scripts/
    ├── run_status.py          (read/write Run Status)
    ├── priority_scorer.py     (AI priority scoring)
    ├── queue_scanner.py       (find new tasks in code)
    ├── verify_cli_docs.py     (check CLI vs README)
    └── rollback_if_unstable.py (auto-revert on failure)
```

## Risk Warnings

> **⚠️ This skill permanently changes agent behavior.**

- Agent auto-commits, auto-releases, auto-modifies code
- One agent × one project only
- Disable cron job to pause; uninstall skill to stop
- User requests are always force-queued (score=100)

## Install via ClawHub

The latest version is always on ClawHub:

**https://clawhub.ai/weiminglu1/autonomous-improvement-loop**

## License

MIT-0 — Free to use, modify, and redistribute. No attribution required.
