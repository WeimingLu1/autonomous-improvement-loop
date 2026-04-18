---
name: autonomous-improvement-loop
description: "AUTONOMOUS IMPROVEMENT LOOP | ONE AGENT x ONE PROJECT | CRON-DRIVEN DEV QUEUE
WARNING: PERSISTENT AUTO-DEV MODE -- auto-commits, auto-releases, auto-modifies files
Disable cron to pause. Uninstall to stop."
---

# Autonomous Improvement Loop

> **⚠️ BEFORE INSTALLING — READ THIS**
>
> Installing this skill **changes your agent's behavior permanently**. Once activated:
> - The agent enters **continuous development mode** — it will auto-commit, auto-release, and auto-modify code without asking
> - **One agent × one project only** — the agent becomes dedicated to this single project
> - **Cron job required** — you must configure a cron job to trigger the loop
> - **Disable the cron job** to pause the loop; uninstall the skill to stop it entirely
> - User requests are **always force-queued** (score=100, inserted at #1)
>
> If you want a human-in-the-loop model where the agent asks before every change, **do not install this skill**.

---

## What This Skill Does

Transforms your agent into a **self-sustaining development machine** for a single project.

This skill works with **both new and existing projects**:

- **Existing project** → AI takes over maintenance immediately, runs your improvement queue autonomously
- **New project** → AI helps you bootstrap the foundation, then transitions to autonomous mode once ready

**Two operational modes:**

| Mode | When triggered | What happens |
|------|---------------|-------------|
| **Bootstrap Mode** | Project is new or not yet AI-ready | AI tells you what's missing, helps you set up the foundation, waits for you to finish |
| **Normal Loop** | Project has basic structure + non-empty queue | AI executes queue tasks autonomously, commits, releases, reports |

---

## Project Readiness Check

Every cron trigger runs a readiness check before deciding what to do:

```
Is VERSION file present?
  NO → Bootstrap Mode: tell user "project not initialized, here's what to create first"
  YES ↓

Is pytest passing?
  NO → Bootstrap Mode: tell user "pytest must pass before AI can manage this project"
  YES ↓

Is HEARTBEAT.md queue empty?
  YES → Bootstrap Mode: suggest initial queue items, wait for user to confirm
  NO ↓

Normal Loop: execute top queue task
```

---

## Bootstrap Mode — For New Projects

When the project is too new for AI management, the agent will:

1. **Detect what's missing** — VERSION, src/ structure, tests, docs, etc.
2. **Tell you clearly** — what the project needs before AI can take over
3. **Suggest a bootstrap queue** — a set of foundational tasks to make the project AI-ready
4. **Wait** — cron keeps firing, agent keeps checking readiness, does nothing until ready
5. **Auto-switch** — once project passes readiness check, agent automatically enters Normal Loop

**Example bootstrap queue for a new Python CLI project:**

| # | Type | Task | Why needed |
|---|------|------|-------------|
| 1 | feature | Initialize project structure (src/, tests/, pyproject.toml) | Foundation for AI to work |
| 2 | feature | Add VERSION file and basic CLI entrypoint | AI needs version tracking |
| 3 | feature | Write first passing test | AI needs tests to validate changes |
| 4 | feature | Set up README with install instructions | Project needs user-facing docs |
| 5 | feature | Configure GitHub repo and CI | AI needs to commit and release |

Once these 5 items are done, the project passes readiness check → Normal Loop begins automatically.

---

## Normal Loop — For Established Projects

For projects that already have basic structure, the agent:

1. Reads the queue from HEARTBEAT.md
2. Executes the top pending task
3. Commits, pushes, runs pytest
4. Creates GitHub Release
5. Updates docs
6. Announces to Telegram
7. Scans for the next improvement opportunity
8. Waits for next cron trigger

---

## Architecture

| Layer | What | Where |
|-------|------|-------|
| Skill state | SKILL.md, config.md, HEARTBEAT.md, DEVLOG.md | `skills/autonomous-improvement-loop/` |
| Scripts | run_status, priority_scorer, queue_scanner, verify_cli_docs, rollback_if_unstable | `skills/autonomous-improvement-loop/scripts/` |
| Agent prompts | Queue system rules, pre-commit checklist | `skills/autonomous-improvement-loop/prompts/` |
| Project code | Source, README, VERSION, docs/ | `~/Projects/YOUR_PROJECT/` |
| Trigger | OpenClaw cron (every 30 min, isolated session) | `openclaw cron list` |
| Reporting | Telegram | Chat ID in config.md |

**Key principle**: All loop state stays in the skill directory — the project directory is only for code.

---

## Queue System

### HEARTBEAT.md Structure

```markdown
## Run Status

| Field | Value |
|-------|-------|
| last_run_time | — |
| last_run_commit | — |
| last_run_result | unknown |
| last_run_task | — |
| cron_lock | false |
| rollback_on_fail | true |
| mode | bootstrap |  ← "bootstrap" or "normal"

## Queue

| # | Type | Score | Content | Source | Status | Created |
|---|------|-------|---------|--------|--------|---------|
| 1 | feature | 65 | [[Feature]] Add dark mode toggle | user | pending | 2026-04-18 |
```

### Priority Algorithm

```
score = 100                  → User request (forced to #1, all others shift down)
score = 90-100               → Bug that breaks core functionality
score = 70-89                → Bug in non-core feature
score = 65-79               → Important feature enhancement
score = 50-64               → General feature
score = 30-49               → Internal improvement (tests, docs)

Tiebreaker: older creation time wins
```

### Queue Minimum Size

After each cron execution, the loop **ensures the queue has at least 5 pending items** by running `refresh_queue` (queue_scanner --refresh --min 5). This keeps the backlog healthy even when many small tasks get done in sequence.

The scanner draws from **10 creative buckets**, not just code hygiene:
- `test` / `service` — missing unit tests
- `todo` / `doc` — code cleanliness
- `cli` — missing CLI features (--json, completions)
- `ux` — user experience improvements
- `feature` — new feature ideas
- `intelligence` — smart/AI-adjacent features (insights, predictions, anomaly detection)
- `data` — import/export/integration
- `engage` — retention & engagement (achievements, streaks, health scores)

Higher-impact buckets (intelligence, engage, feature) score 65-72; internal improvements score 45-55.

### cron_lock — How Serialization Works

| Step | User | Cron |
|------|------|------|
| 1 | User sends request | Cron fires (isolated session) |
| 2 | Check: cron_lock? | Set cron_lock = true |
| 3 | cron_lock=false --> join queue (#1) | Execute task, commit+push |
| 4 | No collision possible | Set cron_lock = false, announce |

**No file locks needed** — cron runs in an isolated session; user and cron never execute simultaneously.

---

## Complete Execution Flow (8 Steps)

```
① cron fires (every 30 min, isolated session, 1h timeout)
       │
       ▼
② cron_lock = true
       │
       ▼
③ Project Readiness Check
       ├─ VERSION missing?  --> Bootstrap Mode (announce what's missing)
       ├─ pytest failing?   --> Bootstrap Mode (tell user to fix tests)
       ├─ queue empty?      --> Bootstrap Mode (suggest initial queue)
       └─ all checks pass   --> Normal Loop
       │
─── [ Bootstrap Mode: report to user, wait for next cron ] ───

④ Read Queue → AI re-score → sort → take top task
       │
⑤ Implement (pytest green throughout)
       │
⑥ git add + commit + push
       │
⑦ rollback_if_unstable.py
       ├─ pytest pass → continue
       └─ pytest fail → git revert + write fail status + announce rollback
       │
⑧ Update docs (README.md, project docs/)
       │
⑨ Release: VERSION bump → git tag → gh release create
       │
⑩ cron_lock = false + run_status.py write
       │
⑪ Announce to Telegram
       │
⑫ refresh_queue.py (queue_scanner --refresh --min 5)
       │     └─ keeps adding candidates until queue has ≥5 pending items
       │
⑬ Update memory/YYYY-MM-DD.md
       │
STOP — wait for next cron trigger
```

---

## Setup (3 Steps — Single Command)

Use `init.py` as the single entry point. It auto-detects everything.

### Step 1: Run `init.py adopt` (接管已有项目)

```bash
python scripts/init.py adopt ~/Projects/YOUR_PROJECT
```

**What it does — automatically:**
1. Detects project path, GitHub repo, CLI name, language
2. Reads existing `config.md` to reuse values
3. Checks project readiness (VERSION, pytest, git, README)
4. Writes `config.md`
5. Detects or creates Cron Job (every 30 min, isolated session)
6. Initializes `HEARTBEAT.md`
7. Prints a full status report

```bash
# 查看项目就绪状态
python scripts/init.py status ~/Projects/YOUR_PROJECT

# 完全交互式（自动检测所有信息）
python scripts/init.py adopt

# 从零初始化新项目
python scripts/init.py onboard ~/Projects/NEW_PROJECT
```

### Step 2: Done

`init.py adopt` handles everything. If it cannot detect something (Agent ID, Chat ID), it tells you what to set manually.

### Step 3: Verify

```bash
openclaw cron list
python scripts/init.py status ~/Projects/YOUR_PROJECT
```

---

## Telegram Report Template

**Language**: All text in the report (title, body, commit message, release notes) is generated in the language specified by `project_language` in `config.md`.

**English version:**
```
✅ 【Completed: Task Name】

What it is:
(Plain language, no jargon)

Why it matters:
(User perspective benefit)

How to use:
(Concrete command/example)

Test results:
pytest N passed

New queue:
#bug: (count) | #feature: (count remaining)

Commit: HASH
Release: v0.0.X → URL
```

**Chinese version (project_language: zh):**
```
✅ 【已完成: 任务名称】

这是什么：
（简单易懂地描述）

为什么重要：
（对用户有什么实际好处）

怎么用：
（具体命令或示例）

测试结果：
pytest N passed

当前队列：
#bug: (count) | #feature: (count remaining)

Commit: HASH
Release: v0.0.X → URL
```

---

## Risk Warnings

> **⚠️ IMPORTANT — READ BEFORE ENABLING**

### 🔴 Permanent Behavior Change
Installing this skill **permanently changes agent behavior**. The agent will no longer ask for confirmation before making commits, releasing versions, or modifying project files.

### 🔴 One Project Only
This skill dedicates one agent to one project. If your agent has other responsibilities, they may be affected when the cron loop runs.

### 🔴 Auto-Commit + Auto-Release
Every completed task triggers:
- `git commit && git push`
- `git tag && gh release create`
- README.md updates
- Version number increment

### 🔴 Bootstrap Waits, Not Panics
When your project is new and not ready, the agent **will not crash or spam you**. It will calmly report what's missing on the first cron, then wait silently on subsequent crons until you fix it.

### 🟡 How to Pause
Disable the loop without uninstalling the skill:
```bash
openclaw cron delete YOUR_CRON_JOB_ID
```

### 🟡 How to Stop Completely
```bash
openclaw cron delete YOUR_CRON_JOB_ID
clawhub uninstall autonomous-improvement-loop
```

---

## Prerequisites

- [ ] `gh` CLI authenticated (`gh auth status`)
- [ ] Project cloned locally (`~/Projects/PROJECT`)
- [ ] Telegram chat ID known
- [ ] OpenClaw agent ID known

**Run `bootstrap.py --report` first** — it checks everything else (VERSION, pytest, structure) and tells you exactly what your project needs.

---

## Script Reference

| Script | Purpose | Key Command |
|--------|---------|-------------|
| `init.py` | **Main entry point** — adopt existing project or onboard new one; auto-detects all settings | `adopt [--project PATH] [--agent ID] [--chat-id ID] [--language en|zh]` / `status [project]` / `onboard project` |
| `bootstrap.py` | Legacy wizard (replaced by init.py) | `--project . --skill-dir . --report` |
| `run_status.py` | Read/write Run Status (incl. cron_lock, mode) | `--heartbeat HEARTBEAT.md read` |
| `priority_scorer.py` | Generate AI scoring prompt (rule fallback) | `--task "..." --type improve` |
| `queue_scanner.py` | Scan project + append 1 candidate (--scan); or refresh queue to ≥5 items (--refresh) | `--project . --heartbeat HEARTBEAT.md [--language zh] [--refresh --min 5]` |
| `verify_cli_docs.py` | Check CLI vs README alignment | `--project . [--cli-name health]` |
| `rollback_if_unstable.py` | Push → pytest → auto git revert on fail | `--project . --heartbeat HEARTBEAT.md --task "..."` |

---

## Files Summary

| What | Where |
|------|-------|
| Skill state | `skills/autonomous-improvement-loop/` |
| Queue + Status | `skills/autonomous-improvement-loop/HEARTBEAT.md` |
| Archive | `skills/autonomous-improvement-loop/DEVLOG.md` |
| Project binding | `skills/autonomous-improvement-loop/config.md` |
| Cron registration | `openclaw cron list` |
| Project code | `~/Projects/PROJECT/` |
