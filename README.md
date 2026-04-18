# Autonomous Improvement Loop

**One agent. One project. Cron-driven autonomous development queue.**

[![ClawHub](https://img.shields.io/badge/Install-ClawHub-6B57FF?style=flat-square)](https://clawhub.ai/weiminglu1/autonomous-improvement-loop)
[![License: MIT](https://img.shields.io/badge/License-MIT-green?style=flat-square)](LICENSE)

---

## What Is This?

A skill for [OpenClaw](https://github.com/openclaw/openclaw) agents that turns your agent into a **self-sustaining development machine** for a single project.

Once installed and configured:

- Your agent continuously improves your project on a schedule (cron-driven)
- All improvement tasks go through an AI-prioritized queue (HEARTBEAT.md)
- Every completed task → `git commit` → `git push` → GitHub Release → Telegram report
- Queue stays full automatically — the scanner keeps finding new tasks
- The agent never loses context — it remembers the queue across sessions

## Two Modes

### Normal Loop — For Established Projects

Your agent picks the highest-priority task from the queue, implements it, commits, releases, and reports back. No manual intervention needed.

### Bootstrap Mode — For New Projects

If your project is too new (no VERSION, no tests, empty queue), the agent enters Bootstrap Mode. It tells you exactly what's missing and waits until you're ready — it won't touch your code until the foundation is in place.

## Quick Start

### 1. Install

```bash
clawhub install autonomous-improvement-loop
```

### 2. One-Command Onboarding

```bash
# 接管已有项目（保留现有队列）
python scripts/init.py adopt ~/Projects/YOUR_PROJECT --agent YOUR_AGENT_ID --chat-id YOUR_CHAT_ID --language zh

# 新项目引导
python scripts/init.py onboard ~/Projects/YOUR_PROJECT --agent YOUR_AGENT_ID --chat-id YOUR_CHAT_ID --language zh

# 查看项目状态
python scripts/init.py status ~/Projects/YOUR_PROJECT
```

| Subcommand | Use case |
|------------|----------|
| `adopt` | 接管已有项目，保留现有队列，自动创建/更新 cron |
| `onboard` | 新项目引导，生成初始队列，设置 cron |
| `status` | 查看项目就绪状态、队列内容、cron 状态 |

### 3. Cron Starts Automatically

After `adopt` or `onboard`, the cron job is created and runs every 30 minutes. No manual cron setup needed.

---

## How It Works

```
Cron fires (every 30 min)
    │
    ▼
Acquire cron_lock (prevent concurrent runs)
    │
    ▼
Read queue (HEARTBEAT.md) → pick top task by score
    │
    ▼
Implement + pytest
    │
    ▼
git add → commit → push
    │
    ▼
pytest → auto-revert on failure (rollback_on_fail)
    │
    ▼
VERSION bump + GitHub Release
    │
    ▼
Telegram report to owner
    │
    ▼
Refresh queue (queue_scanner.py) if pending < 5
    │
    ▼
Release cron_lock → wait for next cron
```

---

## Queue Priority

| Score | Meaning |
|-------|---------|
| 100 | User request (forced to #1 immediately) |
| 90-100 | Bug breaking core functionality |
| 70-89 | Bug in non-core feature |
| 65-79 | Important feature enhancement |
| 50-64 | General feature / internal improvement |
| 30-49 | Tests, docs, code quality |

**Queue rules:**
- User request → score=100 → inserted at #1, all others shift down
- During cron execution (cron_lock=true): user requests can still queue, agent refuses direct file edits
- After any addition: re-sort by score descending, rewrite HEARTBEAT.md
- Scanner refresh: if pending < 5, scan code for new candidates automatically

---

## File Structure

```
autonomous-improvement-loop/
├── SKILL.md                  # Skill definition (for OpenClaw)
├── README.md                 # This file
├── config.md                 # Project binding configuration
├── HEARTBEAT.md              # Queue + Run Status (the agent's memory)
├── DEVLOG.md                 # Completed tasks archive
├── prompts/
│   └── QUEUE_SYSTEM_PROMPT.md   # System prompt for queue operations
└── scripts/
    ├── init.py               # Uni entry point: adopt / onboard / status
    ├── queue_scanner.py      # Scan code → append candidates to queue
    ├── priority_scorer.py    # AI priority scoring for queue entries
    ├── run_status.py         # Read/write Run Status section
    ├── verify_cli_docs.py    # Check CLI help vs README consistency
    └── rollback_if_unstable.py  # Auto-revert on pytest failure
```

---

## Skill Lifecycle

### Install → Configure → Adopt

```bash
# 1. Install from ClawHub
clawhub install autonomous-improvement-loop

# 2. Configure project binding
# (init.py adopt does this automatically, or edit config.md manually)

# 3. One-command adopt
python scripts/init.py adopt ~/Projects/YOUR_PROJECT \
  --agent YOUR_AGENT_ID \
  --chat-id YOUR_CHAT_ID \
  --language zh
```

### config.md Fields

```markdown
project_path: ~/Projects/YOUR_PROJECT
repo: https://github.com/OWNER/REPO
version_file: ~/Projects/YOUR_PROJECT/VERSION
docs_agent_dir: ~/Projects/YOUR_PROJECT/docs/agent
cli_name: your-cli
agent_id: YOUR_AGENT_ID
chat_id: "YOUR_CHAT_ID"
project_language: zh          # "zh" = Chinese output, "en" = English
cron_schedule: "*/30 * * * *"
cron_timeout: 3600
cron_job_id: "uuid-here"
```

---

## Risk Warnings

> **⚠️ This skill permanently changes agent behavior.**

- Agent auto-commits, auto-releases, auto-modifies code
- One agent × one project only
- Disable cron job to pause: `openclaw cron delete <job-id>`
- User requests are always force-queued at score=100
- `rollback_on_fail: true` — pytest failure triggers automatic git revert

---

## Install via ClawHub

The latest version is always on ClawHub:

**https://clawhub.ai/weiminglu1/autonomous-improvement-loop**

## License

MIT-0 — Free to use, modify, and redistribute. No attribution required.
