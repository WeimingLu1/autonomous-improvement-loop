# Autonomous Improvement Loop — Design Specification

> Status: Draft

---

## Core Concept

One agent installs this skill, enters **autonomous improvement守护模式**: continuously monitors a task queue, periodically executes the highest-priority item, and reports results to the user. All improvement state lives inside the skill — it does not pollute the project codebase.

**Design principles**:
- Single-project: one agent maintains one project
- Queue serialization: user and cron share the same queue — no concurrent conflicts
- AI-prioritized: urgent breaking bugs > feature impact > queue order
- User requests always jump to #1

---

## Architecture

### Scripts

| Script | Role |
|--------|------|
| `init.py` | adopt / onboard / status — main setup tool |
| `project_insights.py` | Scan project, generate type-specific improvement candidates |
| `priority_scorer.py` | Score queue entries (supports user request insertion) |
| `verify_and_revert.py` | Run verification, rollback on failure |
| `run_status.py` | Read/write Run Status section in HEARTBEAT.md |
| `bootstrap.py` | Legacy helper (Python-only, pre-v6 projects) |
| `queue_scanner.py` | **Legacy** — redirects to `project_insights.py` |
| `rollback_if_unstable.py` | **Legacy** — redirects to `verify_and_revert.py` |

### Project Type Support

| Type | Indicators | Description |
|------|-----------|-------------|
| `software` | `src/`, `tests/`, `Cargo.toml` | Code / CLI / library projects |
| `writing` | `chapters/`, `outline.md` | Novels, scripts, blog posts |
| `video` | `scripts/`, `scenes/`, `storyboard/` | Film, documentary, footage |
| `research` | `papers/`, `references/`, `*.tex` | Academic papers, literature reviews |
| `generic` | any directory | Any structured long-term work |

### Queue Format (HEARTBEAT.md)

| Field | Values |
|-------|--------|
| `Type` | `improve` \| `feature` \| `fix` \| `wizard` \| `user` |
| `Score` | 1–100 (higher = more urgent; user requests = 100) |
| `Source` | `scanner` \| `user` \| `agent` |
| `Status` | `pending` \| `done` \| `skip` |

### Cron Execution Sequence

```
1. cron_lock = true
2. pick top queue task
3. agent executes → git commit
4. verify_and_revert.py (if verification_command configured)
5. report + update HEARTBEAT.md
6. queue refreshed if below minimum
7. cron_lock = false
```

---

## Config (config.md)

```yaml
project_path: .
project_kind:           # software | writing | video | research | generic (auto-detected)
project_language: en   # zh = Chinese, en = English
github_repo: https://github.com/OWNER/REPO
verification_command:
publish_command:
cron_schedule: "*/30 * * * *"
cron_enabled: true
```

---

## Verification

`verify_and_revert.py` reads `verification_command` from `config.md`:

- **Empty** → mark task `unverified`, no rollback
- **Configured** → run it; on non-zero exit → auto-revert last commit

---

## HEARTBEAT.md Structure

```
## Run Status
## Queue
## Done Log
---
```

### Run Status Fields

| Field | Description |
|-------|-------------|
| `last_run_time` | ISO timestamp |
| `last_run_commit` | Git hash |
| `last_run_result` | `pass` \| `fail` \| `unverified` |
| `last_run_task` | Task description |
| `cron_lock` | `true` = someone is editing queue, skip this run |
| `mode` | `bootstrap` \| `normal` |
| `rollback_on_fail` | `true` = auto-revert on verification failure |
