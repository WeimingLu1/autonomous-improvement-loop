#!/usr/bin/env python3
r"""
Autonomous Improvement Loop — setup wizard & cron hosting CLI

Supports these flows:
  a-adopt   Take over an existing project (auto-detect, configure, start)
  a-onboard Bootstrap a brand-new project
  a-status  Check project readiness and queue state

  a-start   Start cron hosting (create cron job from config.md)
  a-stop    Stop cron hosting (remove cron job)
  a-add     Create a user-sourced TASK + full plan doc
  a-current Show current task + full plan doc
  a-plan    Generate current task + full plan (PM mode)
  a-log     Show recent roadmap Done Log entries
  a-refresh [deprecated: use a-plan]
  a-trigger Execute current roadmap task
  a-config  Get or set config values

Examples:
  # Take over an existing project (most common)
  python init.py a-adopt ~/Projects/YOUR_PROJECT

  # Bootstrap a new project
  python init.py a-onboard ~/Projects/MyProject

  # Check project readiness
  python init.py a-status ~/Projects/YOUR_PROJECT

  # Start cron hosting
  python init.py a-start

  # Stop cron hosting
  python init.py a-stop

  # Add a user request as a full task plan
  python init.py a-add "Implement dark mode support"

  # Show current task
  python init.py a-current

  # Show recent roadmap log
  python init.py a-log -n 10

  # Generate next PM task
  python init.py a-plan

  # Execute current roadmap task
  python init.py a-trigger

  # Read a config value
  python init.py a-config get project_language

  # Set a config value
  python init.py a-config set project_language zh

All parameters are optional. init.py auto-detects project path, GitHub repo,
Agent ID, and Telegram Chat ID whenever possible, and only prompts when needed.
"""

from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

if str(Path(__file__).resolve().parent.parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Import all commands and utilities from split modules
from scripts.cli import (
    cmd_adopt,
    cmd_onboard,
    cmd_status,
    cmd_add,
    cmd_plan,
    cmd_current,
    cmd_queue,
    cmd_log,
    cmd_trigger,
    cmd_config,
    cmd_switch,
    cmd_maintenance,
)
from scripts.cron import cmd_start, cmd_stop
from scripts.detect import detect_project_path, detect_openclaw_agent_id, detect_telegram_chat_id
from scripts.state import resolve_language


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Autonomous Improvement Loop setup wizard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Usage examples:

              # Take over an existing project (most common)
              python init.py a-adopt ~/Projects/YOUR_PROJECT

              # Bootstrap a new project
              python init.py a-onboard ~/Projects/MyProject

              # Check project readiness
              python init.py a-status ~/Projects/YOUR_PROJECT

              # Start cron hosting
              python init.py a-start

              # Stop cron hosting
              python init.py a-stop

              # Add a user requirement
              python init.py a-add "Implement dark mode support"

              # Trigger queue scan
              python init.py a-scan

              # Clear non-user tasks
              python init.py a-clear

              # Show current queue
              python init.py a-queue

              # Show recent done log
              python init.py a-log -n 10

              # Full queue refresh (clear + scan)
              python init.py a-refresh

              # Trigger cron immediately
              python init.py a-trigger

              # Read config value
              python init.py a-config get project_language

              # Write config value
              python init.py a-config set project_language zh
            """),
    )

    sub = parser.add_subparsers(dest="command", required=True)

    adopt_p = sub.add_parser("a-adopt", help="Take over an existing project")
    adopt_p.add_argument("project", nargs="?", type=Path)
    adopt_p.add_argument("--agent", help="OpenClaw Agent ID")
    adopt_p.add_argument("--chat-id", help="Telegram Chat ID")
    adopt_p.add_argument("--language", "--lang", "-l", default=None,
                         choices=["en", "zh"],
                         help="Project output language")
    adopt_p.add_argument("--model", "-m", default="",
                         help="LLM model for cron sessions (empty = use OpenClaw default)")
    adopt_p.add_argument("--force-new-cron", action="store_true",
                         help="Force recreation of the Cron Job (replace existing)")
    adopt_p.set_defaults(func=cmd_adopt)

    onboard_p = sub.add_parser("a-onboard", help="Bootstrap a new project from scratch")
    onboard_p.add_argument("project", nargs="?", type=Path)
    onboard_p.add_argument("--agent", help="OpenClaw Agent ID")
    onboard_p.add_argument("--chat-id", help="Telegram Chat ID")
    onboard_p.add_argument("--language", "--lang", "-l", default=None,
                          choices=["en", "zh"],
                          help="Project output language")
    onboard_p.add_argument("--model", "-m", default="",
                          help="LLM model for cron sessions (empty = use OpenClaw default)")
    onboard_p.set_defaults(func=cmd_onboard)

    status_p = sub.add_parser(
        "a-status",
        description="检查项目就绪状态：AIL 配置、cron 状态、ROADMAP 队列情况",
        help="Check project readiness",
    )
    status_p.add_argument("project", nargs="?", type=Path,
                          default=detect_project_path(),
                          help="Project path (auto-detected if omitted)")
    status_p.add_argument("--all", action="store_true", help="Show all registered projects")
    status_p.add_argument("--language", "--lang", "-l", default=None,
                          choices=["en", "zh"],
                          help="Output language (default: Chinese)")
    status_p.epilog = textwrap.dedent("""\
        Examples:
          python init.py a-status                  # Auto-detect project
          python init.py a-status ~/Projects/myapp # Specify project
          python init.py a-status --language en    # English output
        """)
    status_p.set_defaults(func=cmd_status)

    start_p = sub.add_parser("a-start", help="Start cron托管 (create cron job)")
    start_p.set_defaults(func=lambda _a: cmd_start())

    stop_p = sub.add_parser("a-stop", help="Stop cron托管 (remove cron job)")
    stop_p.set_defaults(func=lambda _a: cmd_stop())

    add_p = sub.add_parser("a-add", help="Create a user-sourced TASK + full plan doc")
    add_p.add_argument("content", nargs="+", help="Requirement content text")
    add_p.set_defaults(func=lambda a: cmd_add(" ".join(a.content)))

    plan_p = sub.add_parser(
        "a-plan",
        description="生成当前 PM 任务并输出完整 Plan 文档（ROADMAP.md + plans/TASK-*.md）",
        help="Generate current task and full plan (PM mode)",
    )
    plan_p.add_argument("--force", action="store_true", help="Regenerate even if current task exists")
    plan_p.add_argument("--count", "-n", type=int, default=1, help="Number of tasks to generate (default: 1)")
    plan_p.add_argument("--dry-run", action="store_true", help="Show what would be generated without writing anything")
    plan_p.epilog = textwrap.dedent("""\
        Examples:
          python init.py a-plan            # Generate next task
          python init.py a-plan --force    # Force regeneration
          python init.py a-plan -n 3       # Generate 3 tasks at once
          python init.py a-plan --dry-run  # Preview without writing
        """)
    plan_p.set_defaults(func=lambda a: cmd_plan(force=a.force, count=a.count, dry_run=a.dry_run))

    current_p = sub.add_parser(
        "a-current",
        description="显示当前执行中的任务及其完整 Plan 文档内容",
        help="Show current task + full plan doc",
    )
    current_p.add_argument("--verbose", "-v", action="store_true", help="Show full plan doc")
    current_p.epilog = textwrap.dedent("""\
        Examples:
          python init.py a-current           # Show current task summary
          python init.py a-current --verbose # Show full plan doc
        """)
    current_p.set_defaults(func=lambda a: cmd_current(verbose=a.verbose))

    queue_p = sub.add_parser("a-queue", help="[deprecated: use a-current]")
    queue_p.add_argument("--all", action="store_true", help="Include done items")
    queue_p.set_defaults(func=lambda _a: cmd_current())

    log_p = sub.add_parser("a-log", help="Show recent Done Log entries")
    log_p.add_argument("-n", "--count", type=int, default=10,
                      help="Number of entries to show (default: 10)")
    log_p.set_defaults(func=lambda a: cmd_log(n=a.count))

    refresh_p = sub.add_parser("a-refresh", help="[deprecated alias: use a-plan]")
    refresh_p.set_defaults(func=lambda _a: cmd_plan(force=True))

    trigger_p = sub.add_parser(
        "a-trigger",
        description="立即执行当前 ROADMAP 任务，触发 autonomous-improvement-loop 工作流",
        help="Execute current roadmap task immediately",
    )
    trigger_p.add_argument("--force", action="store_true",
                          help="Re-run even if current task is already marked doing")
    trigger_p.add_argument("--no-spawn", action="store_true",
                          help="Skip spawning a new cron session — record result directly")
    trigger_p.add_argument("--dry-run", action="store_true",
                          help="Show what would happen without writing or committing")
    trigger_p.epilog = textwrap.dedent("""\
        Examples:
          python init.py a-trigger            # Execute current task
          python init.py a-trigger --force    # Re-run even if already doing
          python init.py a-trigger --no-spawn # Record result without cron
          python init.py a-trigger --dry-run  # Preview without writing
        """)
    trigger_p.set_defaults(func=lambda a: cmd_trigger(force=a.force, no_spawn=a.no_spawn, dry_run=a.dry_run))

    config_sp = sub.add_parser("a-config", help="Get or set config values")
    config_sp.add_argument("action", choices=["get", "set"],
                          help="'get' to read a value, 'set' to write")
    config_sp.add_argument("key", help="Config key (e.g. project_language)")
    config_sp.add_argument("value", nargs="?", help="New value (required for 'set')")
    config_sp.set_defaults(func=lambda a: cmd_config(action=a.action, key=a.key, value=a.value))

    switch_p = sub.add_parser("a-switch", help="Switch active project (by alias or path)")
    switch_p.add_argument("alias_or_path", help="Project alias or absolute path")
    switch_p.add_argument("--language", "--lang", "-l", default=None, choices=["en", "zh"])
    switch_p.set_defaults(func=lambda a: cmd_switch(alias_or_path=a.alias_or_path, language=a.language))

    maint_p = sub.add_parser("a-maintenance", help="Manage maintenance mode")
    maint_p.add_argument("action", choices=["on", "off", "status"], nargs="?", default="status")

    args = parser.parse_args()

    # Auto-detect project path if not given
    if hasattr(args, "project") and args.project is None:
        detected = detect_project_path()
        if detected:
            print(f"Auto-detected project: {detected}")
            args.project = detected
        else:
            print("Error: could not auto-detect a project path. Pass one explicitly or run inside a project directory.")
            print("\nNo Git repository was found in:")
            print("  ~/Projects/")
            print("  ~/projects/")
            print("  ~/Code/")
            print("\nSpecify one manually, for example: python init.py adopt ~/Projects/YourProject")
            parser.parse_args(["a-adopt", "--help"])
            sys.exit(1)

    # Auto-detect agent_id
    if hasattr(args, "agent") and not args.agent:
        args.agent = detect_openclaw_agent_id()

    # Auto-detect chat_id
    if hasattr(args, "chat_id") and not getattr(args, "chat_id", None):
        args.chat_id = detect_telegram_chat_id()

    # Auto-detect language
    if hasattr(args, "language") and not args.language:
        args.language = resolve_language(getattr(args, "project", None), explicit=None)

    try:
        if args.command == "a-adopt":
            cmd_adopt(
                project=args.project,
                agent_id=args.agent,
                chat_id=args.chat_id,
                language=args.language,
                model=args.model,
                force_new_cron=args.force_new_cron,
            )
        elif args.command == "a-onboard":
            cmd_onboard(
                project=args.project,
                agent_id=args.agent,
                chat_id=args.chat_id,
                language=args.language,
                model=args.model,
            )
        elif args.command == "a-status":
            cmd_status(args.project, language=args.language, all_projects=args.all)
        elif args.command == "a-start":
            cmd_start()
        elif args.command == "a-stop":
            cmd_stop()
        elif args.command == "a-add":
            cmd_add(" ".join(args.content))
        elif args.command == "a-plan":
            cmd_plan(force=args.force, count=args.count, dry_run=args.dry_run)
        elif args.command == "a-current":
            cmd_current(verbose=args.verbose)
        elif args.command == "a-queue":
            cmd_current(verbose=False)
        elif args.command == "a-log":
            cmd_log(n=args.count)
        elif args.command == "a-refresh":
            cmd_plan(force=True)
        elif args.command == "a-trigger":
            cmd_trigger(force=args.force, no_spawn=args.no_spawn, dry_run=args.dry_run)
        elif args.command == "a-config":
            cmd_config(action=args.action, key=args.key, value=args.value)
        elif args.command == "a-maintenance":
            cmd_maintenance(action=args.action)
    except KeyboardInterrupt:
        print("\n\nCancelled.")
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())