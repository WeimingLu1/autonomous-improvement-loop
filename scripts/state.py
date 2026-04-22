"""
State management — path helpers, config I/O, CLI output utilities,
and state-mutation helpers (create_cron, delete_cron, seed_queue).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from .detect import (
    detect_openclaw_agent_id,
    detect_telegram_chat_id,
    detect_existing_cron,
    check_project_readiness,
    write_config,
)

# ── Constants ─────────────────────────────────────────────────────────────────

HERE = Path(__file__).parent.resolve()
SKILL_DIR = HERE.parent

CONFIG_FILE = Path.home() / ".openclaw" / "skills-config" / "autonomous-improvement-loop" / "config.md"

DEFAULT_SCHEDULE_MS = 30 * 60 * 1000   # 30 min
DEFAULT_TIMEOUT_S = 3600                # 1 hour
DEFAULT_LANGUAGE = "en"

# ── AIL State Path Helpers ────────────────────────────────────────────────────

def ail_state_dir(project: Path) -> Path:
    """Return the .ail/ state directory for a project."""
    return project / ".ail"


def ail_project_md(project: Path) -> Path:
    """Path to PROJECT.md for a project."""
    return project / ".ail" / "PROJECT.md"


def ail_roadmap(project: Path) -> Path:
    """Path to ROADMAP.md for a project."""
    return project / ".ail" / "ROADMAP.md"


def ail_plans_dir(project: Path) -> Path:
    """Path to plans/ directory for a project."""
    return project / ".ail" / "plans"


def ail_config(project: Path) -> Path:
    """Path to project-level config.md for a project."""
    return project / ".ail" / "config.md"


# ── Backward Compatibility Migration ──────────────────────────────────────────

def _migrate_to_ail(project: Path) -> bool:
    """Migrate legacy project-root state files to .ail/ directory."""
    legacy_files = {
        project / "ROADMAP.md": ail_roadmap(project),
        project / "PROJECT.md": ail_project_md(project),
        project / "config.md": ail_config(project),
    }
    legacy_dirs = {
        project / "plans": ail_plans_dir(project),
    }

    needs_migration = False
    for old_path in list(legacy_files) + list(legacy_dirs):
        if old_path.exists():
            needs_migration = True
            break

    if not needs_migration:
        return False

    ail_dir = ail_state_dir(project)
    ail_dir.mkdir(parents=True, exist_ok=True)

    migrated = False

    for old_path, new_path in legacy_files.items():
        if old_path.exists() and not new_path.exists():
            shutil.move(str(old_path), str(new_path))
            migrated = True

    for old_path, new_path in legacy_dirs.items():
        if old_path.exists() and old_path.is_dir() and not new_path.exists():
            shutil.move(str(old_path), str(new_path))
            migrated = True

    return migrated


# ── Config path helpers ────────────────────────────────────────────────────────

def _config_template() -> Path:
    """Path to the skill's template config (shipped with the package)."""
    return SKILL_DIR / "config.md"


def read_current_config() -> dict[str, str]:
    """Read existing config values. Falls back to template if persistent config missing."""
    conf_file = CONFIG_FILE if CONFIG_FILE.exists() else _config_template()
    if not conf_file.exists():
        return {}
    text = read_file(conf_file)
    result = {}
    for line in text.splitlines():
        m = re.match(r"^(\w[\w_]*):\s*(.+)$", line.strip())
        if m:
            value = re.sub(r"\s+#.*$", "", m.group(2)).strip()
            result[m.group(1)] = value
    return result


# ── CLI Output Utilities ───────────────────────────────────────────────────────

COLOR_RESET = "\033[0m"
COLOR_GREEN = "\033[32m"
COLOR_YELLOW = "\033[33m"
COLOR_RED = "\033[31m"
COLOR_BLUE = "\033[34m"
COLOR_BOLD = "\033[1m"


def c(text: str, color: str) -> str:
    return f"{color}{text}{COLOR_RESET}"


def ok(msg: str) -> None:
    print(f"  {COLOR_GREEN}✓{COLOR_RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {COLOR_YELLOW}⚠{COLOR_RESET} {msg}")


def info(msg: str) -> None:
    print(f"  {COLOR_BLUE}ℹ{COLOR_RESET} {msg}")


def fail(msg: str) -> None:
    print(f"  {COLOR_RED}✗{COLOR_RESET} {msg}", file=sys.stderr)


def step(msg: str) -> None:
    print(f"\n{COLOR_BOLD}{msg}{COLOR_RESET}")


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, **kwargs)


def ask(prompt: str, default: str | None = None) -> str:
    if default:
        prompt = f"{prompt} [{default}]"
    result = input(f"  {prompt}: ").strip()
    return result if result else (default or "")


def read_file(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def write_file(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


# ── Cron helpers ───────────────────────────────────────────────────────────────

def resolve_language(project: Path | None = None, explicit: str | None = None) -> str:
    from .detect import detect_project_language, detect_agent_language
    if explicit:
        return explicit
    if project:
        lang = detect_project_language(project)
        if lang:
            return lang
    agent_lang = detect_agent_language()
    if agent_lang:
        return agent_lang
    return DEFAULT_LANGUAGE


def create_cron(agent_id: str, model: str, chat_id: str | None) -> str:
    """Create an OpenClaw cron job and return its ID."""
    config = read_current_config()
    project_path = config.get("project_path", "").strip()
    cron_schedule = config.get("cron_schedule", "*/30 * * * *").strip() or "*/30 * * * *"
    cron_timeout = config.get("cron_timeout", str(DEFAULT_TIMEOUT_S)).strip() or str(DEFAULT_TIMEOUT_S)
    roadmap_path = str(ail_roadmap(Path(project_path))) if project_path else ".ail/ROADMAP.md"

    cron_message = (
        f"Autonomous Improvement Loop — execute task, record result, report back.\n\n"
        f"Project: {project_path or '(unset)'}\n\n"
        f"Your workflow (use exec tool for all shell commands):\n"
        f"1. exec: read {CONFIG_FILE} and {roadmap_path}\n"
        f"2. exec: read the current task plan `.ail/plans/TASK-xxx.md`\n"
        f"3. DO the work — implement, run tests, verify acceptance criteria\n"
        f"4. exec: commit changes with git\n"
        f"5. exec ONLY AFTER all work is verified done: run `python3 {SKILL_DIR / 'scripts' / 'init.py'} a-trigger --force`\n"
        f"   - This updates the Done Log in ROADMAP.md — do NOT send summary before this completes\n"
        f"6. exec ONLY AFTER step 5 completes: read the updated ROADMAP to get next task info\n"
        f"7. Send Telegram summary (via message tool) ONLY AFTER step 6.\n\n"
        f"IMPORTANT:\n"
        f"- Use exec tool for EVERY step — do NOT just describe what to do\n"
        f"- Never send Telegram summary before step 5 completes\n"
        f"- Always send the Telegram summary as your final reply."
    )

    cron_cmd = [
        "openclaw", "cron", "add",
        "--name", "Autonomous Improvement Loop",
        "--cron", cron_schedule,
        "--timeout-seconds", cron_timeout,
        "--agent", agent_id,
        "--session", "isolated",
        "--message", cron_message,
    ]
    if model:
        cron_cmd.extend(["--model", model])
    if chat_id:
        cron_cmd.extend(["--announce", "--channel", "telegram", "--to", chat_id])

    result = subprocess.run(cron_cmd, capture_output=True, text=True, timeout=20)
    if result.returncode != 0:
        raise RuntimeError(f"cron add failed: {result.stderr.strip() or result.stdout.strip()}")

    combined = (result.stdout or "") + "\n" + (result.stderr or "")
    m = re.search(r"[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}", combined)
    if m:
        return m.group(0)
    output = result.stdout.strip()
    return output.split("\n")[0] if output else "unknown"


def delete_cron(cron_id: str) -> None:
    subprocess.run(["openclaw", "cron", "delete", cron_id], capture_output=True, timeout=10)


def seed_queue(project: Path, mode: str, language: str) -> None:
    """Seed the roadmap with an initial task."""
    from scripts.roadmap import init_roadmap, set_current_task, CurrentTask
    from scripts.task_planner import get_seed_task
    from scripts.task_ids import next_task_id
    from scripts.plan_writer import write_plan_doc

    roadmap_path = ail_roadmap(project)
    init_roadmap(roadmap_path)

    plans_dir = ail_plans_dir(project)
    plans_dir.mkdir(parents=True, exist_ok=True)

    seed = get_seed_task(project, mode, language)
    task_id = next_task_id(plans_dir)
    plan_path = write_plan_doc(
        plans_dir=plans_dir,
        task_id=task_id,
        title=seed.title,
        task_type=seed.task_type,
        source=seed.source,
        effort=seed.effort,
        context=seed.context,
        why_now=seed.why_now,
        scope=seed.scope,
        non_goals=seed.non_goals,
        relevant_files=seed.relevant_files,
        execution_plan=seed.execution_plan,
        acceptance_criteria=seed.acceptance_criteria,
        verification=seed.verification,
        risks=seed.risks,
        background=seed.background,
        rollback=seed.rollback,
    )

    from datetime import datetime, timezone
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    task = CurrentTask(
        task_id=task_id,
        task_type=seed.task_type,
        source=seed.source,
        title=seed.title,
        status="pending",
        created=created,
    )
    set_current_task(
        roadmap_path, task,
        plan_path=str(plan_path.relative_to(project / ".ail")),
        next_default_type="idea",
        improves_since_last_idea=0,
        reserved_user_task_id="",
    )