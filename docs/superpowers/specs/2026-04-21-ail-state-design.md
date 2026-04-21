# AIL State Directory — Project-State Isolation Design

> **Date:** 2026-04-21
> **Author:** Mia

## Goal

Move ALL skill-generated runtime files into a dedicated `.ail/` subdirectory inside the托管项目, replacing scattered files across the project root and workspace. This keeps project directories clean and follows PM logic: everything about a project lives inside the project.

## Directory Structure

```
托管项目（project_path）/
├── .ail/                      ← ALL skill-generated state lives here
│   ├── HEARTBEAT.md          ← queue + run status
│   ├── PROJECT.md            ← project overview snapshot
│   ├── ROADMAP.md            ← PM roadmap (current task, done log)
│   ├── plans/                 ← TASK-001.md … TASK-N.md
│   │   └── TASK-001.md
│   └── config.md              ← project-level config override
├── src/
├── tests/
└── ...

~/.openclaw/skills-config/autonomous-improvement-loop/config.md  ← skill-level config (remains)
~/.openclaw/workspace-mia/skills/autonomous-improvement-loop/     ← skill code itself (remains)
```

## Files to Migrate

From project root → `.ail/`:
- `ROADMAP.md` → `.ail/ROADMAP.md`
- `HEARTBEAT.md` → `.ail/HEARTBEAT.md`
- `PROJECT.md` → `.ail/PROJECT.md`
- `plans/` → `.ail/plans/`
- `config.md` → `.ail/config.md`

## Code Changes

### 1. `scripts/init.py` — Path Constants

Old (broken):
```python
STATE_DIR = Path.home() / ".openclaw" / "skills-state" / "autonomous-improvement-loop"
HEARTBEAT = STATE_DIR / "HEARTBEAT.md"       # WRONG: never created
PROJECT_MD = STATE_DIR / "PROJECT.md"         # WRONG: never created
CONFIG_FILE = Path.home() / ".openclaw" / "skills-config" / "autonomous-improvement-loop" / "config.md"
```

New:
```python
# State files live in .ail/ inside the托管项目 (project_path)
# Paths are computed dynamically per-project; no fixed STATE_DIR at module level.
HEARTBEAT = None       # computed per-call as project / ".ail" / "HEARTBEAT.md"
PROJECT_MD = None      # computed per-call
# CONFIG_FILE stays in ~/.openclaw/skills-config/ (skill-level config)
```

Better approach: compute paths as functions:

```python
def ail_state_dir(project: Path) -> Path:
    """Return the .ail/ state directory for a project."""
    return project / ".ail"

def ail_path(project: Path, filename: str) -> Path:
    return ail_state_dir(project) / filename

def ail_plans_dir(project: Path) -> Path:
    return ail_state_dir(project) / "plans"
```

### 2. All `project / "ROADMAP.md"` → `ail_path(project, "ROADMAP.md")`

Affected lines in init.py:
- line 609, 871, 1215, 1366, 1576, 1618
- Also in `seed_queue()`, `cmd_plan()`, `cmd_current()`, `cmd_trigger()`, `cmd_log()`

### 3. All `project / "plans"` → `ail_plans_dir(project)`

Affected:
- `plans_dir = project / "plans"` → `plans_dir = ail_plans_dir(project)`
- line 1211, 1378, 1649

### 4. HEARTBEAT path

Replace `HEARTBEAT` constant usage with `ail_path(project, "HEARTBEAT.md")`.

### 5. PROJECT_MD path

Replace `PROJECT_MD` constant usage with `ail_path(project, "PROJECT.md")`.

### 6. `scripts/roadmap.py` — `init_roadmap()`, `load_roadmap()`, `set_current_task()`, `append_done_log()`

All take `path: Path` as argument — no change needed, caller passes correct path.

### 7. `scripts/plan_writer.py` — `write_plan_doc()`

Takes `plans_dir: Path` — caller passes `ail_plans_dir(project)`. No change needed.

### 8. `scripts/task_ids.py` — `next_task_id()`

Takes `plans_dir: Path` — caller passes `ail_plans_dir(project)`. No change needed.

### 9. `.gitignore`

Replace:
```
HEARTBEAT.md
ROADMAP.md
plans/
config.md
```

With:
```
.ail/
```

### 10. `scripts/init.py` — Cron Message

Update the cron message (line 1093) to reference `{project}/.ail/ROADMAP.md` instead of `{STATE_DIR}/ROADMAP.md`.

## Migration Steps

1. Create `.ail/` directory in project
2. Move `HEARTBEAT.md`, `PROJECT.md`, `ROADMAP.md`, `plans/`, `config.md` into `.ail/`
3. Update code paths
4. Verify `a-status`, `a-plan`, `a-current` work correctly
5. Clean up workspace-level `HEARTBEAT.md` from `~/.openclaw/workspace-mia/`

## Backward Compatibility

None needed — this is a breaking change for existing adoptions. Users must re-adopt their projects after the change (or we can add a migration helper that moves existing files automatically).

A migration helper in `init.py` can detect old-location files and auto-migrate:
```python
def _migrate_to_ail(project: Path) -> None:
    """Migrate legacy project-root state files to .ail/. Run once."""
    from_path = lambda f: project / f
    to_path = lambda f: ail_path(project, f)
    for fname in ["HEARTBEAT.md", "PROJECT.md", "ROADMAP.md"]:
        old = from_path(fname)
        new = to_path(fname)
        if old.exists() and not new.exists():
            shutil.move(old, new)
    # plans/
    if (project / "plans").exists() and not ail_plans_dir(project).exists():
        shutil.move(project / "plans", ail_plans_dir(project))
    # config.md
    old_cfg = project / "config.md"
    new_cfg = ail_path(project, "config.md")
    if old_cfg.exists() and not new_cfg.exists():
        shutil.move(old_cfg, new_cfg)
```

## Test Plan

1. Run `python scripts/init.py a-status` — should find `.ail/ROADMAP.md` and work
2. Run `python scripts/init.py a-plan` — should create plan in `.ail/plans/`
3. Run `python scripts/init.py a-current` — should read from `.ail/`
4. Verify no files in project root (outside `.ail/`)
