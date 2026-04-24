"""
CLI commands — all cmd_* functions for the autonomous-improvement-loop CLI.
Each command is a public entry point registered in init.py's typer app.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import signal
import subprocess
import sys
import textwrap
import threading
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# Re-export state helpers so existing imports from init.py still work
from .file_lock import FileLock
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
    load_config,
    read_file,
    write_file,
    COLOR_YELLOW,
    COLOR_BOLD,
    COLOR_RED,
    COLOR_GREEN,
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

from enum import Enum, auto


class DryRunMode(Enum):
    """Dry-run level for CLI commands.

    OFF      — real execution (default)
    PLAN_ONCE — a-plan dry-run: show task that would be generated but don't write ROADMAP.md
    FULL     — a-trigger dry-run: show everything that would happen without writing anything
    """

    OFF = auto()
    PLAN_ONLY = auto()   # used by a-plan
    FULL = auto()        # used by a-trigger (and any future FULL dry-run)

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
    detect_existing_crons,
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
            post_feature_maintenance_remaining=roadmap.post_feature_maintenance_remaining,
            maintenance_anchor_title=roadmap.maintenance_anchor_title,
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
        plan_path=str(plan_path.relative_to((project / ".ail").resolve())),
        next_default_type=roadmap.next_default_type,
        improves_since_last_idea=roadmap.improves_since_last_idea,
        post_feature_maintenance_remaining=roadmap.post_feature_maintenance_remaining,
        maintenance_anchor_title=roadmap.maintenance_anchor_title,
        reserved_user_task_id="",
    )
    ok(f"User request saved as {task_id}")
    print()
    _print_plan_doc(plan_path)


# ── cmd_status ────────────────────────────────────────────────────────────────

def cmd_status(project: Path, language: str | None = None, all_projects: bool = False) -> None:
    from scripts.roadmap import normalize_roadmap
    from scripts.i18n import get_message, get_lang
    from scripts.multi_project import cmd_status_all

    if all_projects:
        cmd_status_all()
        return

    lang = get_lang(language)
    _ = lambda key: get_message(key, lang)

    step(_("checking_project_status"))

    if project is None:
        detected = detect_project_path()
        if not detected:
            fail(_("no_project_found"))
            sys.exit(1)
        project = detected

    _migrate_to_ail(project)

    readiness = check_project_readiness(project)
    roadmap_path = ail_roadmap(project)
    config = read_current_config()

    print(f"\n  {c(_('project'), COLOR_BOLD)} {project.name}")
    print(f"  {c(_('path'), COLOR_BOLD)} {project}")

    step(_("readiness_checks"))
    all_ok = True
    for check, result in readiness.items():
        if result:
            ok(check)
        else:
            warn(f"{check} {c(_('missing'), COLOR_YELLOW)}")
            all_ok = False
    print()

    if all_ok:
        ok(_("project_fully_configured"))
    else:
        warn(_("project_has_missing_items"))

    if roadmap_path.exists():
        roadmap = normalize_roadmap(roadmap_path)
        if roadmap.current_task:
            step(_("current_task"))
            ct = roadmap.current_task
            print(f"  {c(_('id'), COLOR_BOLD)} {ct.task_id}")
            print(f"  {c(_('title'), COLOR_BOLD)} {ct.title}")
            print(f"  {c(_('status'), COLOR_BOLD)} {ct.status}")
            print(f"  {c(_('type'), COLOR_BOLD)} {ct.task_type}")
            print(f"  {c(_('created'), COLOR_BOLD)} {ct.created}")
            if roadmap.reserved_user_task_id:
                print(f"  {c(_('reserved_user_task'), COLOR_BOLD)} {roadmap.reserved_user_task_id}")
            print(f"  {c('rhythm', COLOR_BOLD)} next={roadmap.next_default_type}  "
                  f"improves_since_idea={roadmap.improves_since_last_idea}  "
                  f"maint_remaining={roadmap.post_feature_maintenance_remaining}")
            if roadmap.maintenance_anchor_title:
                print(f"  {c('maint_anchor', COLOR_BOLD)} {roadmap.maintenance_anchor_title}")
        else:
            warn(_("no_current_task"))
    else:
        warn(_("roadmap_not_found"))

    print()
    active_crons = detect_existing_crons()
    if active_crons:
        if len(active_crons) == 1:
            ok(f"{_('cron_job_id')}: {active_crons[0]}")
        else:
            warn(f"{_('cron_job_id')}: {', '.join(active_crons)}")
            warn(f"Active cron count = {len(active_crons)} (expected 1)")
    elif config.get("cron_job_id"):
        warn(f"{_('cron_job_id')}: {config['cron_job_id']} (not currently active)")
    else:
        warn(f"  {_('cron_job_not_detected')}")

    print()

    plans_dir = ail_plans_dir(project)
    metrics = _plan_health_snapshot(plans_dir)
    info(
        "plan health: "
        f"count={metrics['plan_count']}  unique_titles={metrics['unique_titles']}  "
        f"duplicates={metrics['duplicate_count']}  duplicate_ratio={metrics['duplicate_ratio']:.1%}"
    )
    top_duplicates = metrics["top_duplicates"]
    if top_duplicates:
        for title, count in top_duplicates[:3]:
            print(f"  dup x{count}: {title}")

    print()

    # Show config source
    from .config import load_config
    yaml_cfg = load_config(project)
    config_yaml_path = project / ".ail" / "config.yaml"
    if config_yaml_path.exists():
        info(f"config: {config_yaml_path} (YAML overrides active)")
        print(f"  schedule_ms={yaml_cfg['schedule_ms']}  "
              f"git_since_days={yaml_cfg['git_since_days']}  "
              f"sticky_threshold={yaml_cfg['sticky_threshold']}  "
              f"trigger_timeout_s={yaml_cfg['trigger_timeout_s']}")
    else:
        info(f"config: using hardcoded defaults (no .ail/config.yaml)")

    print()


# ── Planning commands ──────────────────────────────────────────────────────────

COLOR_BOLD = "\033[1m"

def _get_roadmap_and_project():
    from scripts.roadmap import normalize_roadmap
    config = read_current_config()
    project_path_str = config.get("project_path", "").strip()

    # Self-hosting: when running from inside the skill's own tree,
    # operate on the skill's local .ail/ — even if project_path points
    # somewhere else (allows 'ail' commands to work on the skill itself).
    # This activates only when cwd is the skill root or one level deep.
    cwd = Path.cwd()
    skill_root = Path(__file__).resolve().parent.parent
    in_skill_tree = (
        cwd.resolve() == skill_root.resolve()
        or (cwd.parent.resolve() == skill_root.resolve() and cwd.name == "scripts")
    )
    if in_skill_tree and (cwd / ".ail").exists():
        # Always use the skill's own .ail/ when running from within the skill tree
        project_path_str = str(cwd if cwd.resolve() == skill_root.resolve() else cwd.parent)
    elif not project_path_str or project_path_str in (".", "YOUR_PROJECT_PATH"):
        detected = detect_project_path()
        project_path_str = str(detected) if detected else str(cwd)

    project = Path(project_path_str).expanduser().resolve()
    roadmap_path = ail_roadmap(project)
    if roadmap_path.exists():
        normalize_roadmap(roadmap_path)
    return project, roadmap_path


def _collect_completed_titles(project: Path, roadmap_path: Path, plans_dir: Path) -> set[str]:
    """Collect completed task titles from Done Log, git history, and current project state."""
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

    # Collect done titles from git history via two-pass strategy:
    # Pass 1: find commits whose message mentions TASK-xxx anywhere
    # Pass 2: find commits whose diff touches a plan file (covers task
    #         commits that don't mention TASK- in the message, e.g. "feat(benchmarks)")
    found_task_ids: set[str] = set()

    cfg = load_config()
    git_msg_result = subprocess.run(
        ["git", "log", "--format=%H %s", f"--since={cfg['git_since_days']} days ago"],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=cfg['git_log_timeout'],
    )
    if git_msg_result.returncode == 0:
        for line in git_msg_result.stdout.splitlines():
            parts = line.split(" ", 1)
            if len(parts) < 2:
                continue
            _commit_hash, message = parts[0], parts[1]
            for m in re.finditer(r"(TASK-\d+)", message):
                found_task_ids.add(m.group(1))

    git_diff_result = subprocess.run(
        ["git", "log", "--name-only", "--format=%H", f"--since={cfg['git_since_days']} days ago"],
        cwd=project,
        capture_output=True,
        text=True,
        timeout=cfg['git_log_name_only_timeout'],
    )
    if git_diff_result.returncode == 0:
        current_commit = None
        for line in git_diff_result.stdout.splitlines():
            stripped = line.strip()
            if not stripped:
                continue
            if not stripped.startswith(" "):
                # commit hash line
                current_commit = stripped
            elif current_commit and ".ail/plans/" in line and line.strip().endswith(".md"):
                pm = re.search(r"\.ail/plans/(TASK-\d+)\.md", line)
                if pm:
                    found_task_ids.add(pm.group(1))

    # Pass 3: for remaining plan files, search recent git commits for
    # files that the plan itself mentions in its Scope or Relevant Files section.
    # This catches commits that implement a task without TASK- in the message.
    # Example: benchmarks task scope lists scripts/init.py; the benchmarks commit
    # created benchmarks/run_benchmarks.py — we find it by scope file existence.
    _SCRIPT_FILES: set[str] = set()
    try:
        sf_result = subprocess.run(
            ["git", "ls-files", "scripts/", "benchmarks/"],
            cwd=project, capture_output=True, text=True, timeout=cfg['detect_timeout'],
        )
        if sf_result.returncode == 0:
            for f in sf_result.stdout.splitlines():
                _SCRIPT_FILES.add(f.strip())
    except Exception:
        pass

    for plan_file in sorted(plans_dir.glob("TASK-*.md")):
        try:
            plan_text = plan_file.read_text(encoding="utf-8")
        except Exception:
            continue
        first_line = plan_text.splitlines()[0].strip()
        title_m = re.match(r"#\s+TASK-\d+\s+·\s+(.+)$", first_line)
        if not title_m:
            continue
        title = title_m.group(1).strip()
        if title in done_titles:
            continue  # already added via Pass 1 or 2

        # Look for scope file paths mentioned in the plan (## Scope, ## Relevant Files)
        scope_m = re.search(r"(?i)(?:Scope|Relevant Files)[^\n]*\n([\s\S]+?)(?=\n##|\Z)", plan_text)
        if scope_m:
            scope_text = scope_m.group(1)
            # find file paths (with or without directory prefix)
            for file_m in re.finditer(r"(?:scripts|benchmarks|tests|[\w_-]+)\/[\w_\.-]+", scope_text):
                file_ref = file_m.group(0).strip()
                if not file_ref:
                    continue
                # Skip scripts/ scope files — scripts/ is modified in nearly every
                # commit so it cannot reliably identify task completion. Benchmarks
                # and tests scope files are specific enough to be useful signals.
                if file_ref.startswith("scripts/"):
                    continue
                # check if this file was modified in any recent commit
                # (limit to last 20 commits to keep it fast)
                file_result = subprocess.run(
                    ["git", "log", "--format=%H", "-20", f"--{file_ref}"],
                    cwd=project, capture_output=True, text=True, timeout=cfg['detect_timeout'],
                )
                if file_result.returncode == 0 and file_result.stdout.strip():
                    done_titles.add(title)
                    break

    for task_id in found_task_ids:
        plan_path = plans_dir / f"{task_id}.md"
        if not plan_path.exists():
            continue
        try:
            first_line = plan_path.read_text(encoding="utf-8").splitlines()[0].strip()
        except Exception:
            continue
        title_match = re.match(r"#\s+TASK-\d+\s+·\s+(.+)$", first_line)
        if title_match:
            done_titles.add(title_match.group(1).strip())

    done_titles.update(_collect_completed_titles_from_project_state(project))
    return done_titles


def _collect_completed_titles_from_project_state(project: Path) -> set[str]:
    """Infer obviously completed task titles from the current repository state.

    This supplements Done Log / git-history based dedupe for work that landed via
    normal commits but was not tagged with TASK-xxx in commit messages.
    """
    done_titles: set[str] = set()

    # Benchmark suite already exists.
    benchmark_runner = project / "benchmarks" / "run_benchmarks.py"
    gitignore_path = project / ".gitignore"
    if benchmark_runner.exists() and gitignore_path.exists():
        try:
            gitignore_text = gitignore_path.read_text(encoding="utf-8")
        except Exception:
            gitignore_text = ""
        if "benchmarks/results.jsonl" in gitignore_text:
            done_titles.add("为项目增加性能基准测试，跟踪 a-plan / a-current 等命令的响应时间")

    # init.py split already landed.
    split_targets = [project / "scripts" / name for name in ("cli.py", "cron.py", "detect.py", "state.py")]
    init_py = project / "scripts" / "init.py"
    if all(p.exists() for p in split_targets) and init_py.exists():
        try:
            init_lines = len(init_py.read_text(encoding="utf-8").splitlines())
        except Exception:
            init_lines = 10**9
        if init_lines < 400:
            done_titles.add("审视 scripts/ 目录结构，将 2024 行的 init.py 拆分为 cli/、state/、cron/ 三个模块")

    return done_titles


def _extract_plan_title(plan_path: Path) -> str:
    try:
        first_line = plan_path.read_text(encoding="utf-8").splitlines()[0].strip()
    except Exception:
        return ""
    m = re.match(r"#\s+TASK-\d+\s+·\s+(.+)$", first_line)
    return m.group(1).strip() if m else ""


def _collect_done_task_ids(roadmap_path: Path) -> set[str]:
    done_ids: set[str] = set()
    if not roadmap_path.exists():
        return done_ids
    roadmap_text = roadmap_path.read_text(encoding="utf-8")
    done_log_match = re.search(r"## Done Log\n\n([\s\S]*?)(?=\n## |\Z)", roadmap_text, re.IGNORECASE)
    if not done_log_match:
        return done_ids
    for line in done_log_match.group(1).splitlines():
        if not line.strip().startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) >= 7 and cells[1].startswith("TASK-"):
            done_ids.add(cells[1])
    return done_ids


def _collect_done_log_titles(roadmap_path: Path) -> set[str]:
    done_titles: set[str] = set()
    if not roadmap_path.exists():
        return done_titles
    roadmap_text = roadmap_path.read_text(encoding="utf-8")
    done_log_match = re.search(r"## Done Log\n\n([\s\S]*?)(?=\n## |\Z)", roadmap_text, re.IGNORECASE)
    if not done_log_match:
        return done_titles
    for line in done_log_match.group(1).splitlines():
        if not line.strip().startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) >= 7 and cells[1].startswith("TASK-"):
            done_titles.add(cells[4])
    return done_titles


def _collect_pending_plan_titles(plans_dir: Path, done_task_ids: set[str], done_log_titles: set[str], done_titles: set[str]) -> set[str]:
    """Collect titles of pending plan files.

    A plan is pending only if:
    - Its task_id is not in done_task_ids (not yet done),
    - Its title is not in done_log_titles (not completed via Done Log),
    - Its title is not in done_titles (not in the in-progress done set).
    """
    pending_titles: set[str] = set()
    for plan_path in plans_dir.glob("TASK-*.md"):
        if plan_path.stem in done_task_ids:
            continue
        title = _extract_plan_title(plan_path)
        if title and title not in done_log_titles and title not in done_titles:
            pending_titles.add(title)
    return pending_titles


def _collect_forbidden_titles(project: Path, roadmap_path: Path, plans_dir: Path, roadmap, done_titles: set[str]) -> set[str]:
    # forbidden_titles = done_log_titles + pending_plan_titles + done_titles
    # done_log_titles: titles completed via the Done Log (authoritative source)
    # pending_plan_titles: titles from pending plan files not yet in done_log
    # done_titles: ALL completed titles (Done Log + git history + benchmarks);
    #              must also be forbidden to prevent the git-history bypass bug
    forbidden_titles = set(_collect_done_log_titles(roadmap_path))
    forbidden_titles.update(done_titles)  # block titles completed outside Done Log
    forbidden_titles.update(_collect_pending_plan_titles(plans_dir, _collect_done_task_ids(roadmap_path), forbidden_titles, done_titles))
    if roadmap.current_task and roadmap.current_task.status in {"pending", "doing"}:
        forbidden_titles.add(roadmap.current_task.title)
    reserved = roadmap.reserved_user_task_id.strip()
    if reserved:
        reserved_plan = plans_dir / f"{reserved}.md"
        reserved_title = _extract_plan_title(reserved_plan)
        if reserved_title and reserved_title not in done_titles:
            forbidden_titles.add(reserved_title)
    return forbidden_titles


def _plan_health_snapshot(plans_dir: Path) -> dict[str, object]:
    plan_paths = sorted(plans_dir.glob("TASK-*.md")) if plans_dir.exists() else []
    title_counts: dict[str, int] = {}
    for plan_path in plan_paths:
        title = _extract_plan_title(plan_path)
        if title:
            title_counts[title] = title_counts.get(title, 0) + 1
    total = len(plan_paths)
    unique = len(title_counts)
    duplicates = total - unique
    duplicate_ratio = (duplicates / total) if total else 0.0
    top_duplicates = sorted(title_counts.items(), key=lambda item: (-item[1], item[0]))[:5]
    return {
        "plan_count": total,
        "unique_titles": unique,
        "duplicate_count": duplicates,
        "duplicate_ratio": duplicate_ratio,
        "top_duplicates": top_duplicates,
    }


def cmd_plan(force: bool = False, count: int = 1, dry_run: bool = False) -> None:
    dry_run_mode = DryRunMode.PLAN_ONLY if (dry_run or os.environ.get("DRY_RUN") == "1") else DryRunMode.OFF
    if dry_run_mode == DryRunMode.PLAN_ONLY:
        step(f"[dry-run] 🗺️  Would generate {'current task + ' if count == 1 else f'{count} tasks + '}plan{'s' if count > 1 else ''}")
    else:
        step(f"🗺️  Generating {'current task + ' if count == 1 else f'{count} tasks + '}plan{'s' if count > 1 else ''}")
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
    forbidden_titles = _collect_forbidden_titles(project, roadmap_path, plans_dir, roadmap, done_titles)
    language = read_current_config().get("project_language", DEFAULT_LANGUAGE).strip() or "zh"

    # Multi-task mode: generate N tasks
    if count > 1:
        planned_tasks: list = []
        any_consumed = False
        for i in range(count):
            planned, consumed = choose_next_task(project, roadmap, done_titles, language, forbidden_titles=forbidden_titles)
            if consumed:
                any_consumed = True
            done_titles.add(planned.title)  # avoid duplicates in same batch
            forbidden_titles.add(planned.title)
            planned_tasks.append(planned)

        # Write all plan files (or print in dry-run)
        plan_paths: list[Path] = []
        task_ids: list[str] = []
        for i, planned in enumerate(planned_tasks):
            task_id = next_task_id(plans_dir)
            task_ids.append(task_id)
            if dry_run_mode == DryRunMode.OFF:
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
                plan_paths.append(plan_path)
            ok(f"[dry-run] Would create task {task_id} ({i+1}/{count}): {planned.title}" if dry_run_mode == DryRunMode.PLAN_ONLY else f"Task {task_id} ({i+1}/{count}): {planned.title}")

        # Set first task as current, rhythm updated from last task
        first = planned_tasks[0]
        last = planned_tasks[-1]
        created = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        current = CurrentTask(
            task_id=task_ids[0],
            task_type=first.task_type,
            source=first.source,
            title=first.title,
            status="pending",
            created=created,
        )
        next_type = "improve" if roadmap.next_default_type == "idea" else "idea"
        improves = roadmap.improves_since_last_idea + sum(
            1 for p in planned_tasks if p.task_type == "improve"
        )
        maintenance_remaining = roadmap.post_feature_maintenance_remaining
        if any_consumed and maintenance_remaining > 0:
            maintenance_remaining -= 1
        if dry_run_mode == DryRunMode.OFF:
            set_current_task(
                roadmap_path, current,
                plan_path=str(plan_path.relative_to((project / ".ail").resolve())) if plan_paths else "",
                next_default_type=next_type,
                improves_since_last_idea=improves,
                post_feature_maintenance_remaining=maintenance_remaining,
                maintenance_anchor_title=roadmap.maintenance_anchor_title,
                reserved_user_task_id=roadmap.reserved_user_task_id,
            )
        if dry_run_mode == DryRunMode.PLAN_ONLY:
            ok(f"[dry-run] Would set current task to {task_ids[0]} and update ROADMAP.md")
            return
        print()
        _print_plan_doc(plan_paths[0])
        return

    # Single-task mode (default)
    planned, consumed = choose_next_task(project, roadmap, done_titles, language, forbidden_titles=forbidden_titles)
    task_id = next_task_id(plans_dir)
    if dry_run_mode == DryRunMode.OFF:
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
    else:
        plan_path = plans_dir / f"{task_id}.md"  # dummy for dry-run print

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

    maintenance_remaining = roadmap.post_feature_maintenance_remaining - 1 if (consumed and roadmap.post_feature_maintenance_remaining > 0) else roadmap.post_feature_maintenance_remaining
    maintenance_anchor = roadmap.maintenance_anchor_title
    if dry_run_mode == DryRunMode.OFF:
        set_current_task(
            roadmap_path, task,
            plan_path=str(plan_path.relative_to((project / ".ail").resolve())),
            next_default_type=next_type,
            improves_since_last_idea=improves,
            post_feature_maintenance_remaining=maintenance_remaining,
            maintenance_anchor_title=maintenance_anchor,
            reserved_user_task_id=roadmap.reserved_user_task_id,
        )
    if dry_run_mode == DryRunMode.PLAN_ONLY:
        ok(f"[dry-run] Would create task {task_id}: {planned.title}")
        ok(f"[dry-run] Would write plan doc to {plans_dir / f'{task_id}.md'}")
        ok(f"[dry-run] Would set current task and update ROADMAP.md")
        return
    ok(f"Task {task_id} generated and set as current")
    print()
    _print_plan_doc(plan_path)


def cmd_current(verbose: bool = False) -> None:
    """Show current task + full plan doc.

    Args:
        verbose: If True, print full plan doc; otherwise show task summary.
    """
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
        if verbose:
            print()
            _print_plan_doc(plan_path)
        else:
            # Brief mode: show plan path and size hint
            size = plan_path.stat().st_size
            print(f"\n  📄 Plan: {plan_path.relative_to(project)}")
            print(f"     ({size} bytes, use --verbose for full content)")
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
        timeout=30,
    )
    return r.stdout.strip() if r.returncode == 0 else "unknown"


def _execute_task_plan(project: Path, task) -> tuple[bool, str]:
    cfg = load_config()
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
        timeout=cfg['trigger_timeout_s'],
    )

    if result.returncode == 0:
        return True, "Verification passed"
    else:
        return False, f"Verification failed (exit {result.returncode}): {result.stderr.strip() or result.stdout.strip()}"


TRIGGER_TIMEOUT_S = 300  # 5 minutes default timeout for a-trigger execution


class _TimeoutError(Exception):
    def __init__(self, timeout_s: int):
        self.timeout_s = timeout_s
        super().__init__(f"Trigger timed out after {timeout_s} seconds")


def _timeout_call(func, timeout_s: int, *args, **kwargs) -> None:
    """Run func(*args, **kwargs) with a timeout. Raises _TimeoutError on timeout."""
    result = [None]
    exception = [None]

    def target():
        try:
            result[0] = func(*args, **kwargs)
        except Exception as e:
            exception[0] = e

    t = threading.Thread(target=target, daemon=True)
    t.start()
    t.join(timeout=timeout_s)
    if t.is_alive():
        raise _TimeoutError(timeout_s)
    if exception[0]:
        raise exception[0]
    return result[0]


def _cleanup_stale_locks(project: Path) -> None:
    """Force-release any stale trigger.lock files."""
    lock_path = ail_state_dir(project) / "trigger.lock"
    try:
        if lock_path.exists():
            lock_path.unlink()
    except Exception:
        pass


def cmd_trigger(force: bool = False, no_spawn: bool = False, dry_run: bool = False) -> None:
    dry_run_mode = DryRunMode.FULL if (dry_run or os.environ.get("DRY_RUN") == "1") else DryRunMode.OFF
    if dry_run_mode == DryRunMode.FULL:
        step("[dry-run] ⚡ Would trigger plan execution")
    else:
        step("⚡ Triggering plan execution")
    project, roadmap_path = _get_roadmap_and_project()
    _migrate_to_ail(project)
    if not roadmap_path.exists():
        fail("ROADMAP.md not found. Run a-plan first.")
        sys.exit(1)

    lock_path = ail_state_dir(project) / "trigger.lock"
    lock = FileLock(lock_path, timeout=5.0)
    if not lock.acquire():
        fail(f"Another trigger is already running. Lock held at {lock_path}")
        sys.exit(1)

    try:
        if dry_run_mode == DryRunMode.FULL:
            # Show what would happen without executing
            from scripts.roadmap import load_roadmap
            roadmap = load_roadmap(roadmap_path)
            if roadmap.current_task:
                current = roadmap.current_task
                ok(f"[dry-run] Would execute task: {current.task_id} — {current.title}")
                ok(f"[dry-run] Would call _record_result_only() → writes Done Log to ROADMAP.md")
                ok(f"[dry-run] Would call _maybe_update_project_md() → regenerates .ail/PROJECT.md")
            else:
                ok("[dry-run] No current task to execute")
            ok("[dry-run] Would NOT write git commit")
            return

        if os.environ.get("OPENCLAW_CRON_SESSION") == "1" or no_spawn:
            try:
                _timeout_call(_record_result_only, TRIGGER_TIMEOUT_S, project, roadmap_path, force)
                _timeout_call(_maybe_update_project_md, TRIGGER_TIMEOUT_S, project)
            except _TimeoutError as e:
                fail(f"Trigger timed out after {e.timeout_s} seconds")
                _cleanup_stale_locks(project)
                sys.exit(1)
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
            ["openclaw", "cron", "run", cron_job_id, "--timeout", timeout_ms],
            timeout=int(cron_timeout) + 10,
            env={**os.environ, "OPENCLAW_CRON_SESSION": "1"},
        )
        if r.returncode != 0:
            fail(f"Cron session failed: {(r.stderr or '').strip() or (r.stdout or '').strip() or 'unknown error'}")
            sys.exit(1)
        ok(f"Cron session completed — execution recorded")
    finally:
        lock.release()


def _maybe_update_project_md(project: Path) -> None:
    """Always regenerate .ail/PROJECT.md and append a PM-quality qualitative review."""
    from scripts.project_md import generate_project_md
    project_md_path = ail_project_md(project)
    language = resolve_language(project)
    generate_project_md(project, project_md_path, language=language)
    _pm_review_project_md(project, project_md_path)
    ok("PROJECT.md regenerated + PM review appended")




def _pm_review_project_md(project: Path, project_md_path: Path) -> None:
    """Append a PM-quality qualitative review to PROJECT.md based on recent git changes."""
    import subprocess, re
    from datetime import datetime, timezone
    from scripts.config import load_config
    cfg = load_config()

    # Get last commit info
    log_result = subprocess.run(
        ["git", "log", "--oneline", "-5", "--format=%h %s"],
        cwd=project, capture_output=True, text=True, timeout=cfg['git_log_timeout'],
    )
    log_lines = log_result.stdout.strip().split("\n") if log_result.returncode == 0 else []

    diff_result = subprocess.run(
        ["git", "diff", "--stat", "HEAD~1"],
        cwd=project, capture_output=True, text=True, timeout=cfg['git_log_timeout'],
    )
    diff_stats = diff_result.stdout.strip() if diff_result.returncode == 0 else ""

    files_result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD~1"],
        cwd=project, capture_output=True, text=True, timeout=cfg['git_log_timeout'],
    )
    changed_files = [f.strip() for f in files_result.stdout.strip().split("\n") if f.strip()] if files_result.returncode == 0 else []

    has_test = any("test" in f for f in changed_files)
    has_docs = any("docs" in f or "README" in f for f in changed_files)
    has_script = any(f.startswith("scripts/") for f in changed_files)

    summaries = []
    if has_test:
        summaries.append("测试覆盖率提升")
    if has_docs:
        summaries.append("文档更新")
    if has_script:
        summaries.append("脚本模块改进")
    if not summaries:
        summaries.append("工程优化与清理")

    change_summary = "；".join(summaries)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    review_block = (
        "\n\n---\n\n"
        f"## PM Review ({timestamp})\n\n"
        f"**最近变更：** {change_summary}\n\n"
        "| 指标 | 说明 |\n"
        "|------|------|\n"
    )

    if log_lines:
        review_block += f"| 最近 commit | {log_lines[0]} |\n"

    lines_added = 0
    lines_deleted = 0
    if diff_stats:
        for part in diff_stats.split(","):
            part = part.strip()
            if "insertion" in part:
                m = re.search(r"(\d+)", part)
                if m:
                    lines_added = sum(int(x) for x in re.findall(r"(\d+)", part.split("insertion")[0].strip()))
                    break
        for part in diff_stats.split(","):
            part = part.strip()
            if "deletion" in part:
                m = re.search(r"(\d+)", part)
                if m:
                    lines_deleted = sum(int(x) for x in re.findall(r"(\d+)", part.split("deletion")[0].strip()))
                    break

    if lines_added or lines_deleted:
        review_block += f"| 代码增量 | +{lines_added} / -{lines_deleted} 行 |\n"

    review_block += f"| 变更文件数 | {len(changed_files)} |\n"

    existing = project_md_path.read_text(encoding="utf-8") if project_md_path.exists() else ""
    existing = re.sub(r"\n## PM Review \([^\)]+\)[\s\S]*?(?=\n---|\Z)", "", existing)
    existing = existing.rstrip() + review_block
    project_md_path.write_text(existing, encoding="utf-8")

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

    # Auto-transition pending → doing when force is used (cron session scenario)
    if current.status == "pending":
        step(f"Advancing {current.task_id} from pending → doing")
        from scripts.roadmap import CurrentTask
        new_task = CurrentTask(
            task_id=current.task_id,
            task_type=current.task_type,
            source=current.source,
            title=current.title,
            status="doing",
            created=current.created,
        )
        set_current_task(
            roadmap_path,
            task=new_task,
            plan_path=roadmap.current_plan_path,
            next_default_type=roadmap.next_default_type,
            improves_since_last_idea=roadmap.improves_since_last_idea,
            post_feature_maintenance_remaining=roadmap.post_feature_maintenance_remaining,
            maintenance_anchor_title=roadmap.maintenance_anchor_title,
            reserved_user_task_id=roadmap.reserved_user_task_id,
        )
        # Reload roadmap after status update
        roadmap = load_roadmap(roadmap_path)
        current = roadmap.current_task

    roadmap_text = roadmap_path.read_text(encoding="utf-8")
    done_log_match = re.search(r"## Done Log\n\n([\s\S]*?)(?=\n## |\Z)", roadmap_text, re.IGNORECASE)
    skip_generate_next = False
    if done_log_match:
        done_block = done_log_match.group(1)
        escaped_title = re.escape(current.title)
        pass_pattern = re.compile(
            rf"\|\s*[^|]+\s*\|\s*[^|]+\s*\|\s*[^|]+\s*\|\s*[^|]+\s*\|\s*{escaped_title}\s*\|\s*pass\s*\|",
            re.IGNORECASE
        )
        if pass_pattern.search(done_block):
            ok(f"Task '{current.title}' already passed — skipping Done Log record.")
            # If this was a maintenance task, decrement the counter so we don't
            # keep generating the same maintenance task in an infinite loop.
            if roadmap.post_feature_maintenance_remaining > 0:
                new_remaining = roadmap.post_feature_maintenance_remaining - 1
                new_anchor = roadmap.maintenance_anchor_title if new_remaining > 0 else ""
                # Update the roadmap to clear maintenance state before generating next task
                from scripts.roadmap import set_current_task
                set_current_task(
                    roadmap_path,
                    task=None,
                    plan_path="",
                    next_default_type=roadmap.next_default_type,
                    improves_since_last_idea=roadmap.improves_since_last_idea,
                    post_feature_maintenance_remaining=new_remaining,
                    maintenance_anchor_title=new_anchor,
                    reserved_user_task_id=roadmap.reserved_user_task_id,
                )
                skip_generate_next = True
            else:
                _generate_next_task(project, roadmap_path, roadmap)
                return

    if skip_generate_next:
        # Reload roadmap so _generate_next_task sees the updated maintenance counter
        roadmap = load_roadmap(roadmap_path)
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
            post_feature_maintenance_remaining=roadmap.post_feature_maintenance_remaining,
            maintenance_anchor_title=roadmap.maintenance_anchor_title,
            reserved_user_task_id="",
        )
        ok(f"Next user task is now current: {next_task.task_id}")
        return

    done_titles = _collect_completed_titles(project, roadmap_path, plans_dir)
    forbidden_titles = _collect_forbidden_titles(project, roadmap_path, plans_dir, roadmap, done_titles)

    completed_task = roadmap.current_task
    if roadmap.post_feature_maintenance_remaining > 0:
        selection_roadmap = roadmap
    elif completed_task and completed_task.source == "pm" and completed_task.task_type == "idea":
        from scripts.roadmap import RoadmapState
        selection_roadmap = RoadmapState(
            current_task=roadmap.current_task,
            next_default_type=roadmap.next_default_type,
            improves_since_last_idea=roadmap.improves_since_last_idea,
            post_feature_maintenance_remaining=2,
            maintenance_anchor_title=completed_task.title,
            current_plan_path=roadmap.current_plan_path,
            reserved_user_task_id=roadmap.reserved_user_task_id,
        )
    else:
        selection_roadmap = roadmap

    language = read_current_config().get("project_language", DEFAULT_LANGUAGE).strip() or "zh"
    planned, consumed = choose_next_task(project, selection_roadmap, done_titles, language, forbidden_titles=forbidden_titles)
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
    selection_remaining = selection_roadmap.post_feature_maintenance_remaining
    selection_anchor = selection_roadmap.maintenance_anchor_title

    if consumed and selection_remaining > 0:
        maintenance_remaining = selection_remaining - 1
        maintenance_anchor = selection_anchor if maintenance_remaining > 0 else ""
    else:
        maintenance_remaining = 0
        maintenance_anchor = ""
    set_current_task(
        roadmap_path,
        task,
        plan_path=str(plan_path.relative_to((project / ".ail").resolve())),
        next_default_type=next_type,
        improves_since_last_idea=improves,
        post_feature_maintenance_remaining=maintenance_remaining,
        maintenance_anchor_title=maintenance_anchor,
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

def cmd_switch(alias_or_path: str, language: str | None = None) -> None:
    """Switch the active project by alias or path."""
    from scripts.i18n import get_message, get_lang
    from scripts.multi_project import (
        cmd_switch as mp_switch,
        list_registered_projects,
        SKILL_CONFIG_HOME,
        CONFIG_FILE_NAME,
    )

    lang = get_lang(language)
    _ = lambda key: get_message(key, lang)

    step(_("switching_project"))

    projects = list_registered_projects()
    if not projects:
        fail("No projects registered in multi_project.cfg.")
        print(f"  Create {SKILL_CONFIG_HOME / CONFIG_FILE_NAME} first.")
        print("  Format: /path/to/project = Display Name  (one per line, # for comments)")
        sys.exit(1)

    if not mp_switch(alias_or_path):
        fail(f"Project '{alias_or_path}' not found.")
        print("  Available projects:")
        for p in projects:
            print(f"    {p.alias}")
        sys.exit(1)

    ok(f"Switched active project to '{alias_or_path}'")
