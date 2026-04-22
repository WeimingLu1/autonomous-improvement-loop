"""
CLI commands — all cmd_* functions for the autonomous-improvement-loop CLI.
Each command is a public entry point registered in init.py's typer app.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# Re-export state helpers so existing imports from init.py still work
from .state import (
    ail_state_dir,
    ail_project_md,
    ail_roadmap,
    ail_plans_dir,
    ail_config,
    _migrate_to_ail,
    CONFIG_FILE,
    _config_template,
    read_current_config,
    DEFAULT_SCHEDULE_MS,
    DEFAULT_TIMEOUT_S,
    DEFAULT_LANGUAGE,
    read_file,
    write_file,
    c,
    ok,
    warn,
    info,
    fail,
    step,
    run,
    ask,
    resolve_language,
)

# Detection functions (also moved from init.py)
from .detect import (
    detect_project_path,
    detect_github_repo,
    detect_project_language,
    detect_agent_language,
    detect_version_file,
    detect_cli_name,
    detect_openclaw_agent_id,
    detect_telegram_chat_id,
    detect_existing_cron,
    detect_pytest_available,
    detect_any_test_command,
    detect_build_config,
    detect_gh_authenticated,
    _read_kind_from_config,
    check_project_readiness,
    build_config,
    write_config,
)

# State mutations & cron (also in init.py)
from .state import create_cron, delete_cron, seed_queue
from .cron import cmd_start, cmd_stop


# ── Project scaffolding (used by cmd_onboard) ─────────────────────────────────

_KNOWN_TYPES = {
    "software": "Software/CLI project (src/, tests/, build config)",
    "writing": "Writing project (chapters/, outline.md, characters/)",
    "video": "Video/media project (scripts/, scenes/, storyboard/)",
    "research": "Academic/research project (papers/, references/, notes/)",
    "generic": "Generic project (docs/, materials/, README)",
}


def _scaffold_project(project: Path, kind: str) -> None:
    """Create minimal directory structure based on project kind."""
    project.mkdir(parents=True, exist_ok=True)
    if kind == "software":
        (project / "src").mkdir(exist_ok=True)
        (project / "tests").mkdir(exist_ok=True)
        (project / "docs").mkdir(exist_ok=True)
        (project / "docs" / "agent").mkdir(exist_ok=True)
        (project / "src" / ".gitkeep").touch()
        (project / "tests" / ".gitkeep").touch()
    elif kind == "writing":
        (project / "chapters").mkdir(exist_ok=True)
        (project / "characters").mkdir(exist_ok=True)
        (project / "outline.md").write_text("# Outline\n\n", encoding="utf-8")
        (project / "characters" / "README.md").write_text("# Character Settings\n\n", encoding="utf-8")
        (project / "chapters" / ".gitkeep").touch()
    elif kind == "video":
        (project / "scripts").mkdir(exist_ok=True)
        (project / "scenes").mkdir(exist_ok=True)
        (project / "storyboard").mkdir(exist_ok=True)
        (project / "assets").mkdir(exist_ok=True)
        (project / "scripts" / "outline.md").write_text("# Script Outline\n\n", encoding="utf-8")
        (project / "scenes" / ".gitkeep").touch()
    elif kind == "research":
        (project / "papers").mkdir(exist_ok=True)
        (project / "references").mkdir(exist_ok=True)
        (project / "notes").mkdir(exist_ok=True)
        (project / "outline.md").write_text("# Research Outline\n\n", encoding="utf-8")
        (project / "references" / "README.md").write_text("# References\n\n", encoding="utf-8")
    else:
        (project / "docs").mkdir(exist_ok=True)
        (project / "materials").mkdir(exist_ok=True)
        (project / "docs" / "README.md").write_text("# Documentation\n\n", encoding="utf-8")


# ── cmd_adopt ─────────────────────────────────────────────────────────────────

def cmd_adopt(
    project: Path,
    agent_id: str,
    chat_id: str | None,
    language: str,
    model: str = "",
    force_new_cron: bool = False,
) -> None:
    step("🔍 Existing project takeover — setup wizard")

    _migrate_to_ail(project)

    if not project.exists():
        fail(f"Project path does not exist: {project}")
        sys.exit(1)

    repo = detect_github_repo(project)
    version_file = detect_version_file(project)
    docs_dir = project / "docs" / "agent"
    cli_name = detect_cli_name(project)
    try:
        from project_insights import detect_project_type
        from project_md import generate_project_md
        project_kind = detect_project_type(project)
    except Exception:
        project_kind = "generic"
    readiness = check_project_readiness(project)

    print(f"\n  {c('Project:', COLOR_BOLD)} {project.name}")
    print(f"  {c('Path:', COLOR_BOLD)} {project}")
    print(f"  {c('GitHub:', COLOR_BOLD)} {repo or c('Not detected (configure manually later)', COLOR_YELLOW)}")
    print(f"  {c('CLI name:', COLOR_BOLD)} {cli_name}")
    print(f"  {c('Language:', COLOR_BOLD)} {'Chinese' if language == 'zh' else 'English'}")
    print(f"  {c('Project type:', COLOR_BOLD)} {project_kind}")
    print(f"  {c('Agent ID:', COLOR_BOLD)} {agent_id or c('Not detected', COLOR_RED)}")

    step("📋 Project readiness check")
    new_items = sum(1 for v in readiness.values() if not v)
    for check, result in readiness.items():
        if result:
            ok(check)
        else:
            warn(f"{check} {c('(missing)', COLOR_YELLOW)}")
    print()

    if new_items > 3:
        warn(f"Project has {new_items} missing readiness item(s). It is safer to fix them first, or take over now and let the loop stay in bootstrap mode.")
        print("  Continuing anyway... (the loop will wait in bootstrap mode)\n")

    existing_cron = detect_existing_cron()
    if existing_cron and not force_new_cron:
        ok(f"Existing Cron Job: {existing_cron}")
        cron_job_id = existing_cron
        use_existing = ask(
            f"  {c('Cron handling (s=keep, r=delete and recreate)', COLOR_BOLD)}",
            "s",
        ).lower()
        if use_existing == "r":
            delete_cron(existing_cron)
            existing_cron = None
            print("  Deleted the old Cron. A new one will be created.")
        else:
            print("  Keeping the existing Cron.")
    else:
        existing_cron = None

    if not existing_cron:
        if not agent_id:
            fail("Cannot create Cron: Agent ID is not set. Configure the OpenClaw agent first.")
            sys.exit(1)
        if not chat_id:
            warn("Telegram Chat ID is not set. Cron will not send notifications. Continue? [y/N]")
            if ask("  >", "n").lower() != "y":
                sys.exit(0)

        step("⏰ Creating Cron Job")
        try:
            cron_job_id = create_cron(agent_id, model, chat_id)
            ok(f"Cron Job created: {cron_job_id}")
        except Exception as e:
            warn(f"Cron creation failed: {e}")
            warn("Cron was not created. Run it manually with: openclaw cron add ...")
            cron_job_id = None
    else:
        cron_job_id = existing_cron

    step("📝 Writing config.md")
    write_config(
        project_path=project,
        repo=repo or "https://github.com/OWNER/REPO",
        version_file=version_file,
        docs_dir=docs_dir,
        cli_name=cli_name,
        agent_id=agent_id or "YOUR_AGENT_ID",
        chat_id=chat_id or "YOUR_TELEGRAM_CHAT_ID",
        language=language,
        cron_job_id=cron_job_id,
        project_kind=project_kind,
    )
    ok("config.md updated")

    step("🧭 Generating PROJECT.md")
    try:
        from project_md import generate_project_md
        generate_project_md(project, ail_project_md(project), language=language, repo=repo)
        ok("PROJECT.md generated")
    except Exception as e:
        warn(f"PROJECT.md generation failed: {e}")

    mode = "bootstrap" if new_items > 3 else "normal"

    roadmap_path = ail_roadmap(project)
    if not roadmap_path.exists():
        step("🧠 Generating initial roadmap task")
        seed_queue(project=project, mode=mode, language=language)
        ok("Initial roadmap task generated")
    else:
        ok("Existing roadmap state detected, skipped auto-generation")

    print(textwrap.dedent(f"""

    {c('✅ Takeover complete!', COLOR_GREEN + COLOR_BOLD)}

    Project: {project.name}
    Mode: {mode}
    Language: {'Chinese' if language == 'zh' else 'English'}
    Cron: {cron_job_id or 'not created'}

    {'The first run will stay in bootstrap mode until the project is ready' if mode == 'bootstrap' else 'Cron runs automatically every 30 minutes'}


    Trigger Cron manually:
      openclaw cron run {cron_job_id}

    Delete Cron:
      openclaw cron delete {cron_job_id}
    """))


# ── cmd_onboard ───────────────────────────────────────────────────────────────

def cmd_onboard(
    project: Path,
    agent_id: str,
    chat_id: str | None,
    language: str,
    project_kind: str = "software",
    model: str = "",
) -> None:
    step("🚀 Bootstrapping a brand-new project")

    if project.exists() and any(project.iterdir()):
        warn(f"Target directory already exists and is not empty: {project}")
        proceed = ask("Proceed anyway? [y/N]", "n").lower()
        if proceed != "y":
            info("Aborted.")
            return

    step("📁 Creating project structure")
    _scaffold_project(project, project_kind)
    ok(f"Project structure created: {project_kind}")

    if not agent_id:
        agent_id = detect_openclaw_agent_id()
    if not chat_id:
        chat_id = detect_telegram_chat_id()

    step("⏰ Creating Cron Job")
    if not agent_id:
        warn("Agent ID not detected. Skipping cron creation.")
        cron_job_id = None
    else:
        try:
            cron_job_id = create_cron(agent_id, model, chat_id)
            ok(f"Cron Job created: {cron_job_id}")
        except Exception as e:
            warn(f"Cron creation failed: {e}")
            cron_job_id = None

    repo = detect_github_repo(project) or "https://github.com/OWNER/REPO"
    version_file = detect_version_file(project)
    docs_dir = project / "docs" / "agent"
    cli_name = detect_cli_name(project)

    step("📝 Writing config.md")
    write_config(
        project_path=project,
        repo=repo,
        version_file=version_file,
        docs_dir=docs_dir,
        cli_name=cli_name,
        agent_id=agent_id or "YOUR_AGENT_ID",
        chat_id=chat_id or "YOUR_TELEGRAM_CHAT_ID",
        language=language,
        cron_job_id=cron_job_id,
        project_kind=project_kind,
    )
    ok("config.md updated")

    step("🧭 Generating PROJECT.md")
    try:
        from project_md import generate_project_md
        generate_project_md(project, ail_project_md(project), language=language, repo=repo)
        ok("PROJECT.md generated")
    except Exception as e:
        warn(f"PROJECT.md generation failed: {e}")

    step("🧠 Generating initial roadmap task")
    seed_queue(project=project, mode="normal", language=language)
    ok("Initial roadmap task generated")

    print(textwrap.dedent(f"""

    {c('✅ Onboarding complete!', COLOR_GREEN + COLOR_BOLD)}

    Project: {project.name}
    Kind: {project_kind}
    Language: {'Chinese' if language == 'zh' else 'English'}
    Cron: {cron_job_id or 'not created'}

    Run the loop:
      cd {project}
      python3 .openclaw/skills/autonomous-improvement-loop/scripts/init.py a-plan

    Cron runs automatically every 30 minutes.
    """))


# ── cmd_add ───────────────────────────────────────────────────────────────────

def cmd_add(content_text: str) -> None:
    step("📝 Adding user request as current task")

    project, roadmap_path = _get_roadmap_and_project()
    _migrate_to_ail(project)

    if not content_text or not content_text.strip():
        fail("Empty content — nothing to add")
        sys.exit(1)

    content_text = re.sub(r"\s*\n\s*", " ", content_text).strip()

    from scripts.roadmap import load_roadmap, set_current_task, init_roadmap, CurrentTask
    from scripts.task_ids import next_task_id
    from scripts.plan_writer import write_plan_doc

    plans_dir = ail_plans_dir(project)
    plans_dir.mkdir(parents=True, exist_ok=True)
    if not roadmap_path.exists():
        init_roadmap(roadmap_path)
        ok(f"Initialized ROADMAP.md at {roadmap_path}")

    roadmap = load_roadmap(roadmap_path)

    if roadmap.current_task and roadmap.current_task.status == "doing":
        warn(f"Current task {roadmap.current_task.task_id} is doing, not interrupting it")
        task_id = next_task_id(plans_dir)
        plan_path = write_plan_doc(
            plans_dir=plans_dir,
            task_id=task_id,
            title=content_text,
            task_type="user",
            source="user",
            effort="medium",
            context="Direct user request captured via a-add.",
            why_now="User explicitly requested this work and user tasks take priority once the current doing task finishes.",
            scope=[content_text],
            non_goals=["Do not interrupt the currently doing task"],
            relevant_files=["TBD during execution"],
            execution_plan=["Wait for current doing task to finish", "Execute user-requested task next"],
            acceptance_criteria=["Requested change is implemented", "Verification is recorded in the plan execution output"],
            verification=["Run relevant tests or checks for the requested change"],
            risks=["Details may need refinement during implementation"],
            background="",
            rollback="",
        )
        set_current_task(
            roadmap_path,
            roadmap.current_task,
            plan_path=roadmap.current_plan_path,
            next_default_type=roadmap.next_default_type,
            improves_since_last_idea=roadmap.improves_since_last_idea,
            reserved_user_task_id=task_id,
        )
        ok(f"Reserved user task {task_id} for after current doing task")
        print()
        _print_plan_doc(plan_path)
        return

    task_id = next_task_id(plans_dir)
    plan_path = write_plan_doc(
        plans_dir=plans_dir,
        task_id=task_id,
        title=content_text,
        task_type="user",
        source="user",
        effort="medium",
        context="Direct user request captured via a-add.",
        why_now="User explicitly requested this work and user tasks take priority over PM-generated tasks.",
        scope=[content_text],
        non_goals=["Do not expand scope beyond the user request unless required to complete it"],
        relevant_files=["TBD during implementation"],
        execution_plan=["Understand requested change", "Implement the change", "Verify behavior and summarize result"],
        acceptance_criteria=["Requested change is implemented", "The resulting task plan is visible via a-current"],
        verification=["Run relevant tests or checks for the requested change"],
        risks=["User request may need clarification if ambiguous"],
        background="",
        rollback="",
    )
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    task = CurrentTask(
        task_id=task_id,
        task_type="user",
        source="user",
        title=content_text,
        status="pending",
        created=created,
    )
    set_current_task(
        roadmap_path,
        task,
        plan_path=str(plan_path.relative_to(project / ".ail")),
        next_default_type=roadmap.next_default_type,
        improves_since_last_idea=roadmap.improves_since_last_idea,
        reserved_user_task_id="",
    )
    ok(f"User request saved as {task_id}")
    print()
    _print_plan_doc(plan_path)


# ── cmd_status ────────────────────────────────────────────────────────────────

def cmd_status(project: Path) -> None:
    from scripts.roadmap import load_roadmap

    step("📊 Checking project status")

    if project is None:
        detected = detect_project_path()
        if not detected:
            fail("No project found. Run from a project directory or configure project_path.")
            sys.exit(1)
        project = detected

    _migrate_to_ail(project)

    readiness = check_project_readiness(project)
    roadmap_path = ail_roadmap(project)
    config = read_current_config()

    print(f"\n  {c('Project:', COLOR_BOLD)} {project.name}")
    print(f"  {c('Path:', COLOR_BOLD)} {project}")

    step("📋 Readiness checks")
    all_ok = True
    for check, result in readiness.items():
        if result:
            ok(check)
        else:
            warn(f"{check} {c('(missing)', COLOR_YELLOW)}")
            all_ok = False
    print()

    if all_ok:
        ok("Project is fully configured")
    else:
        warn("Project has missing readiness items")

    if roadmap_path.exists():
        roadmap = load_roadmap(roadmap_path)
        if roadmap.current_task:
            step("🧠 Current task")
            ct = roadmap.current_task
            print(f"  {c('ID:', COLOR_BOLD)} {ct.task_id}")
            print(f"  {c('Title:', COLOR_BOLD)} {ct.title}")
            print(f"  {c('Status:', COLOR_BOLD)} {ct.status}")
            print(f"  {c('Type:', COLOR_BOLD)} {ct.task_type}")
            print(f"  {c('Created:', COLOR_BOLD)} {ct.created}")
            if roadmap.reserved_user_task_id:
                print(f"  {c('Reserved user task:', COLOR_BOLD)} {roadmap.reserved_user_task_id}")
        else:
            warn("No current task in ROADMAP.md")
    else:
        warn("ROADMAP.md not found — run a-plan first")

    print()
    if config.get("cron_job_id"):
        ok(f"Cron Job ID: {config['cron_job_id']}")
    else:
        warn("  Cron Job: not detected")

    print()


# ── Planning commands ──────────────────────────────────────────────────────────

COLOR_BOLD = "\033[1m"

def _get_roadmap_and_project():
    config = read_current_config()
    project_path_str = config.get("project_path", "").strip()
    if not project_path_str or project_path_str in (".", "YOUR_PROJECT_PATH"):
        detected = detect_project_path()
        project_path_str = str(detected) if detected else str(Path.cwd())
    project = Path(project_path_str).expanduser().resolve()
    roadmap_path = ail_roadmap(project)
    return project, roadmap_path


def _collect_completed_titles(project: Path, roadmap_path: Path, plans_dir: Path) -> set[str]:
    """Collect completed task titles from Done Log and git history."""
    done_titles: set[str] = set()

    if roadmap_path.exists():
        roadmap_text = roadmap_path.read_text(encoding="utf-8")
        done_log_match = re.search(r"## Done Log\n\n([\s\S]*?)(?=\n## |\Z)", roadmap_text, re.IGNORECASE)
        if done_log_match:
            for line in done_log_match.group(1).splitlines():
                if not line.strip().startswith("|") or "---" in line:
                    continue
                cells = [c.strip() for c in line.split("|")[1:-1]]
                if len(cells) >= 7 and cells[1].startswith("TASK-"):
                    done_titles.add(cells[4])

    git_result = subprocess.run(
        ["git", "log", "--oneline", "--grep=TASK-", "--since=90 days ago"],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if git_result.returncode == 0:
        for line in git_result.stdout.splitlines():
            m = re.search(r"(TASK-\d+)", line)
            if not m:
                continue
            plan_path = plans_dir / f"{m.group(1)}.md"
            if not plan_path.exists():
                continue
            try:
                first_line = plan_path.read_text(encoding="utf-8").splitlines()[0].strip()
            except Exception:
                continue
            title_match = re.match(r"#\s+TASK-\d+\s+·\s+(.+)$", first_line)
            if title_match:
                done_titles.add(title_match.group(1).strip())

    return done_titles


def cmd_plan(force: bool = False) -> None:
    step("🗺️  Generating current task + plan")
    project, roadmap_path = _get_roadmap_and_project()
    _migrate_to_ail(project)
    from scripts.roadmap import load_roadmap, set_current_task, init_roadmap, CurrentTask
    from scripts.task_planner import choose_next_task
    from scripts.task_ids import next_task_id
    from scripts.plan_writer import write_plan_doc

    plans_dir = ail_plans_dir(project)
    plans_dir.mkdir(parents=True, exist_ok=True)

    if not roadmap_path.exists():
        init_roadmap(roadmap_path)
        ok(f"Initialized ROADMAP.md at {roadmap_path}")

    roadmap = load_roadmap(roadmap_path)

    if roadmap.reserved_user_task_id and not force:
        warn(f"User task {roadmap.reserved_user_task_id} is reserved — use --force to regenerate anyway")
        cmd_current()
        return

    if roadmap.current_task and roadmap.current_task.status in ("pending", "doing") and not force:
        ok("Current task already exists. Use --force to regenerate.")
        cmd_current()
        return

    done_titles = _collect_completed_titles(project, roadmap_path, plans_dir)

    language = read_current_config().get("project_language", DEFAULT_LANGUAGE).strip() or "zh"
    planned = choose_next_task(project, roadmap, done_titles, language)

    task_id = next_task_id(plans_dir)
    plan_path = write_plan_doc(
        plans_dir=plans_dir,
        task_id=task_id,
        title=planned.title,
        task_type=planned.task_type,
        source=planned.source,
        effort=planned.effort,
        context=planned.context,
        why_now=planned.why_now,
        scope=planned.scope,
        non_goals=planned.non_goals,
        relevant_files=planned.relevant_files,
        execution_plan=planned.execution_plan,
        acceptance_criteria=planned.acceptance_criteria,
        verification=planned.verification,
        risks=planned.risks,
        background=planned.background,
        rollback=planned.rollback,
    )

    created = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    task = CurrentTask(
        task_id=task_id,
        task_type=planned.task_type,
        source=planned.source,
        title=planned.title,
        status="pending",
        created=created,
    )

    next_type = "improve" if roadmap.next_default_type == "idea" else "idea"
    improves = roadmap.improves_since_last_idea + (1 if planned.task_type == "improve" else 0)

    set_current_task(
        roadmap_path, task,
        plan_path=str(plan_path.relative_to(project / ".ail")),
        next_default_type=next_type,
        improves_since_last_idea=improves,
        reserved_user_task_id=roadmap.reserved_user_task_id,
    )
    ok(f"Task {task_id} generated and set as current")
    print()
    _print_plan_doc(plan_path)


def cmd_current() -> None:
    """Show current task + full plan doc."""
    step("📋 Current task")
    project, roadmap_path = _get_roadmap_and_project()
    _migrate_to_ail(project)

    if not roadmap_path.exists():
        fail("ROADMAP.md not found. Run a-plan first.")
        sys.exit(1)

    from scripts.roadmap import load_roadmap
    roadmap = load_roadmap(roadmap_path)

    if not roadmap.current_task:
        warn("No current task in ROADMAP.md. Run a-plan to generate one.")
        return

    ct = roadmap.current_task
    print(f"  ID:     {ct.task_id}")
    print(f"  Title:  {ct.title}")
    print(f"  Status: {ct.status}")
    print(f"  Type:   {ct.task_type}")
    print(f"  Source: {ct.source}")

    if roadmap.reserved_user_task_id:
        print(f"  Reserved user task: {roadmap.reserved_user_task_id}")

    plan_path = project / ".ail" / (ct.task_id + ".md")
    if not plan_path.exists():
        plan_path = project / ".ail" / "plans" / (ct.task_id + ".md")

    if plan_path.exists():
        print()
        _print_plan_doc(plan_path)
    else:
        print(f"\n  Plan file not found: {plan_path}")


def _print_plan_doc(path: Path) -> None:
    """Print a plan doc to stdout."""
    try:
        text = read_file(path)
        print(text)
    except Exception as e:
        warn(f"Could not print plan doc: {e}")


def cmd_queue(all_items: bool = False) -> None:
    from scripts.task_planner import load_task_queue, PlannedTask

    step("📜 Task queue")
    project, _ = _get_roadmap_and_project()
    plans_dir = ail_plans_dir(project)

    if not plans_dir.exists():
        warn("No plans directory found.")
        return

    tasks = load_task_queue(plans_dir)
    if not tasks:
        warn("No tasks in queue.")
        return

    for t in tasks:
        print(f"  {t.task_id}  [{t.task_type}]  {t.title}")

    print(f"\n  Total: {len(tasks)} tasks")


def cmd_log(n: int = 10) -> None:
    step("📜 Recent Done Log")
    project, roadmap_path = _get_roadmap_and_project()

    if not roadmap_path.exists():
        fail("ROADMAP.md not found.")
        sys.exit(1)

    text = read_file(roadmap_path)
    m = re.search(r"## Done Log\n\n([\s\S]*?)(?=\n## |\Z)", text, re.IGNORECASE)
    if not m:
        warn("No Done Log entries found.")
        return

    lines = m.group(1).splitlines()
    header = None
    data_lines = []
    for line in lines:
        if line.strip().startswith("|") and "---" not in line:
            if header is None:
                header = line
            else:
                data_lines.append(line)

    if header:
        print(f"  {header}")
        print(f"  {'-' * len(header)}")

    for line in data_lines[-n:]:
        print(f"  {line}")


def _git_head_short(project: Path) -> str:
    r = subprocess.run(
        ["git", "rev-parse", "--short", "HEAD"],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=5,
    )
    return r.stdout.strip() if r.returncode == 0 else "unknown"


def _execute_task_plan(project: Path, task) -> tuple[bool, str]:
    plan_path = project / ".ail" / "plans" / f"{task.task_id}.md"
    if not plan_path.exists():
        return False, f"Plan file not found: {plan_path}"

    try:
        content = read_file(plan_path)
    except Exception as e:
        return False, f"Failed to read plan: {e}"

    verification_match = re.search(r"## Verification\n\n```bash\n(.*?)\n```", content, re.DOTALL)
    if not verification_match:
        return True, "No verification block found — task treated as pass"

    verification_script = verification_match.group(1).strip()

    if verification_script.startswith("#") or not verification_script:
        return True, "Comment-only verification — task treated as pass"

    step(f"🔍 Running verification:\n  {verification_script}")

    result = subprocess.run(
        verification_script,
        shell=True,
        cwd=project,
        capture_output=True,
        text=True,
        timeout=300,
    )

    if result.returncode == 0:
        return True, "Verification passed"
    else:
        return False, f"Verification failed (exit {result.returncode}): {result.stderr.strip() or result.stdout.strip()}"


def cmd_trigger(force: bool = False) -> None:
    step("⚡ Triggering plan execution")
    project, roadmap_path = _get_roadmap_and_project()
    _migrate_to_ail(project)
    if not roadmap_path.exists():
        fail("ROADMAP.md not found. Run a-plan first.")
        sys.exit(1)

    if os.environ.get("OPENCLAW_CRON_SESSION") == "1":
        _record_result_only(project, roadmap_path, force)
        _maybe_update_project_md(project)
        return

    config = read_current_config()
    cron_job_id = config.get("cron_job_id", "").strip()
    if not cron_job_id:
        fail("No cron job configured. Run a-start first.")
        sys.exit(1)

    cron_timeout = config.get("cron_timeout", str(DEFAULT_TIMEOUT_S)).strip()
    try:
        timeout_ms = str(int(int(cron_timeout) * 1000))
    except ValueError:
        timeout_ms = str(DEFAULT_TIMEOUT_S * 1000)

    step(f"Starting cron session: {cron_job_id}")
    r = run(
        ["openclaw", "cron", "run", cron_job_id, "--expect-final", "--timeout", timeout_ms],
        timeout=int(cron_timeout) + 10,
        env={**os.environ, "OPENCLAW_CRON_SESSION": "1"},
    )
    if r.returncode != 0:
        fail(f"Cron session failed: {r.stderr.strip() or r.stdout.strip() or 'unknown error'}")
        sys.exit(1)
    ok("Cron session completed")


def _maybe_update_project_md(project: Path) -> None:
    """Update .ail/PROJECT.md if it doesn't exist or is stale."""
    from scripts.project_md import generate_project_md
    project_md_path = ail_project_md(project)
    if not project_md_path.exists():
        generate_project_md(project, project_md_path, language=resolve_language(project))
        ok("Generated initial PROJECT.md")


def _record_result_only(project: Path, roadmap_path: Path, force: bool) -> None:
    """Record task result — called from within a cron session."""
    from scripts.roadmap import load_roadmap, append_done_log, set_current_task, CurrentTask
    roadmap = load_roadmap(roadmap_path)
    if not roadmap.current_task:
        fail("No current task found.")
        sys.exit(1)

    current = roadmap.current_task
    if current.status == "doing" and not force:
        warn(f"Current task {current.task_id} is already doing. Use --force to re-record.")
        sys.exit(1)

    roadmap_text = roadmap_path.read_text(encoding="utf-8")
    done_log_match = re.search(r"## Done Log\n\n([\s\S]*?)(?=\n## |\Z)", roadmap_text, re.IGNORECASE)
    if done_log_match:
        done_block = done_log_match.group(1)
        escaped_title = re.escape(current.title)
        pass_pattern = re.compile(
            rf"\|\s*[^|]+\s*\|\s*[^|]+\s*\|\s*[^|]+\s*\|\s*[^|]+\s*\|\s*{escaped_title}\s*\|\s*pass\s*\|",
            re.IGNORECASE
        )
        if pass_pattern.search(done_block):
            ok(f"Task '{current.title}' already passed — skipping Done Log record.")
            _generate_next_task(project, roadmap_path, roadmap)
            return

    ok(f"Recording result for {current.task_id}: {current.title}")
    exec_ok, exec_msg = _execute_task_plan(project, current)

    commit = _git_head_short(project)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    append_done_log(
        roadmap_path,
        timestamp=timestamp,
        task_id=current.task_id,
        task_type=current.task_type,
        source=current.source,
        title=current.title,
        result="pass" if exec_ok else "fail",
        commit=commit,
    )

    if not exec_ok:
        fail(f"Task execution failed: {exec_msg}")
        sys.exit(1)

    ok(f"Result recorded: {exec_msg}")
    _generate_next_task(project, roadmap_path, roadmap)


def _generate_next_task(project: Path, roadmap_path: Path, roadmap) -> None:
    """Generate the next PM task if no reserved user task is pending."""
    from scripts.roadmap import set_current_task, CurrentTask
    from scripts.plan_writer import write_plan_doc
    from scripts.task_ids import next_task_id
    from scripts.task_planner import choose_next_task

    plans_dir = ail_plans_dir(project)
    plans_dir.mkdir(parents=True, exist_ok=True)

    reserved = roadmap.reserved_user_task_id.strip()
    if reserved:
        reserved_plan = plans_dir / f"{reserved}.md"
        title = reserved
        if reserved_plan.exists():
            first_line = reserved_plan.read_text(encoding="utf-8").splitlines()[0].strip()
            m = re.match(r"#\s+TASK-\d+\s+·\s+(.+)$", first_line)
            title = m.group(1).strip() if m else title
        next_task = CurrentTask(
            task_id=reserved,
            task_type="user",
            source="user",
            title=title,
            status="pending",
            created=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        )
        set_current_task(
            roadmap_path,
            next_task,
            plan_path=str(Path(".ail") / "plans" / f"{reserved}.md"),
            next_default_type=roadmap.next_default_type,
            improves_since_last_idea=roadmap.improves_since_last_idea,
            reserved_user_task_id="",
        )
        ok(f"Next user task is now current: {next_task.task_id}")
        return

    done_titles = _collect_completed_titles(project, roadmap_path, plans_dir)

    language = read_current_config().get("project_language", DEFAULT_LANGUAGE).strip() or "zh"
    planned = choose_next_task(project, roadmap, done_titles, language)
    task_id = next_task_id(plans_dir)
    plan_path = write_plan_doc(
        plans_dir=plans_dir,
        task_id=task_id,
        title=planned.title,
        task_type=planned.task_type,
        source=planned.source,
        effort=planned.effort,
        context=planned.context,
        why_now=planned.why_now,
        scope=planned.scope,
        non_goals=planned.non_goals,
        relevant_files=planned.relevant_files,
        execution_plan=planned.execution_plan,
        acceptance_criteria=planned.acceptance_criteria,
        verification=planned.verification,
        risks=planned.risks,
        background=planned.background,
        rollback=planned.rollback,
    )
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    task = CurrentTask(
        task_id=task_id,
        task_type=planned.task_type,
        source=planned.source,
        title=planned.title,
        status="pending",
        created=created,
    )
    next_type = "improve" if roadmap.next_default_type == "idea" else "idea"
    improves = roadmap.improves_since_last_idea + (1 if planned.task_type == "improve" else 0)
    set_current_task(
        roadmap_path,
        task,
        plan_path=str(plan_path.relative_to(project / ".ail")),
        next_default_type=next_type,
        improves_since_last_idea=improves,
        reserved_user_task_id="",
    )
    ok(f"Next task generated and set as current: {task_id}")


def cmd_config(action: str, key: str, value: str | None = None) -> None:
    conf = CONFIG_FILE if CONFIG_FILE.exists() else _config_template()
    defaults = {
        "project_language": DEFAULT_LANGUAGE,
    }
    if action == "get":
        step(f"⚙  Config: {key}")
        config = read_current_config()
        val = config.get(key, "").strip()
        if val:
            ok(f"{key} = {val}")
        else:
            if conf.exists():
                raw = read_file(conf)
                m = re.search(rf"^(\s*{re.escape(key)}:\s*)(.*)$", raw, re.MULTILINE)
                if m:
                    print(f"  {key} = {m.group(2).strip()}")
                    return
            default_val = defaults.get(key, "")
            if default_val:
                print(f"  {key} = {default_val}")
            else:
                warn(f"Key '{key}' not found in config.md")
    elif action == "set":
        if not value:
            fail("'set' requires a value argument")
            sys.exit(1)
        step(f"⚙  Config: {key} = {value}")
        raw = read_file(conf) if conf.exists() else ""
        current_match = re.search(rf"^\s*{re.escape(key)}:\s*(.+)$", raw, re.MULTILINE)
        if current_match and re.sub(r"\s+#.*$", "", current_match.group(1)).strip() == value:
            ok(f"Set {key} = {value} (unchanged)")
            return
        if re.search(rf"^{re.escape(key)}:", raw, re.MULTILINE):
            new_raw = re.sub(
                rf"(^\s*{re.escape(key)}:\s*).+$",
                rf"\g<1>{value}",
                raw,
                flags=re.MULTILINE,
            )
        else:
            if raw and not raw.endswith("\n"):
                raw += "\n"
            new_raw = raw + f"{key}: {value}\n"
        write_file(CONFIG_FILE, new_raw)
        ok(f"Set {key} = {value}")