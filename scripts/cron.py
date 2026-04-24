"""
Cron commands — cmd_start and cmd_stop.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .state import (
    CONFIG_FILE,
    _config_template,
    read_current_config,
    create_cron,
    delete_cron,
    detect_openclaw_agent_id,
    detect_telegram_chat_id,
    ok,
    warn,
    fail,
    step,
    ask,
    write_file,
    read_file,
)
from .detect import detect_existing_cron, detect_existing_crons


def cmd_start() -> None:
    """Start cron hosting — create a cron job from config.md."""
    step("⏰ Starting Autonomous Improvement Loop cron")

    config = read_current_config()
    agent_id = config.get("agent_id", "").strip()
    if not agent_id:
        agent_id = detect_openclaw_agent_id() or ""
        if not agent_id:
            fail("Agent ID not set. Configure via: python3 scripts/init.py a-config set agent_id YOUR_AGENT_ID")
            return

    chat_id = config.get("chat_id", "").strip() or config.get("telegram_chat_id", "").strip()
    if not chat_id:
        chat_id = detect_telegram_chat_id() or ""
        if not chat_id:
            warn("Telegram Chat ID not set. Notifications will not be sent.")
            proceed = ask("Continue without Telegram? [y/N]", "n").lower()
            if proceed != "y":
                return

    model = config.get("model", "").strip()

    existing_ids = detect_existing_crons()
    if len(existing_ids) > 1:
        warn(f"Found duplicate AIL cron jobs: {', '.join(existing_ids)}")
        keep_id = existing_ids[0]
        for duplicate_id in existing_ids[1:]:
            warn(f"Deleting duplicate cron job: {duplicate_id}")
            delete_cron(duplicate_id)
        existing_ids = [keep_id]

    existing = existing_ids[0] if existing_ids else None
    if existing:
        ok(f"Existing Cron Job found: {existing}")
        use_existing = ask("Use existing cron job? [Y/n]", "y").lower()
        if use_existing != "n":
            _update_cron_job_id(existing)
            ok("Cron job is already running.")
            return
        warn("Deleting existing cron job...")
        delete_cron(existing)

    step("⏰ Creating new cron job")
    try:
        cron_id = create_cron(agent_id, model, chat_id)
    except Exception as e:
        fail(f"Failed to create cron job: {e}")
        return

    _update_cron_job_id(cron_id)
    ok(f"Cron job created and started: {cron_id}")
    print(f"\n  The loop will run automatically every 30 minutes.")
    print(f"  Trigger manually: openclaw cron run {cron_id}")


def cmd_stop() -> None:
    """Stop cron hosting — remove the cron job."""
    step("🛑 Stopping Autonomous Improvement Loop cron")

    existing_ids = detect_existing_crons()
    if not existing_ids:
        warn("No cron job found.")
        return

    ok(f"Found cron job(s): {', '.join(existing_ids)}")
    confirm = ask("Delete these cron job(s)? [y/N]", "n").lower()
    if confirm != "y":
        warn("Aborted.")
        return

    for cron_id in existing_ids:
        delete_cron(cron_id)

    _clear_cron_job_id()

    ok("Cron job(s) removed.")


def _update_cron_job_id(cron_id: str) -> None:
    """Update or add cron_job_id in the skill config file."""
    conf = CONFIG_FILE if CONFIG_FILE.exists() else _config_template()
    raw = read_file(conf) if conf.exists() else ""

    if raw:
        if "cron_job_id:" in raw:
            raw = __import__("re").sub(
                r"(cron_job_id:\s*).*",
                rf"\g<1>{cron_id}",
                raw,
                flags=__import__("re").MULTILINE,
            )
        else:
            raw = raw.rstrip() + f"\ncron_job_id: {cron_id}\n"
    else:
        raw = f"cron_job_id: {cron_id}\n"

    write_file(CONFIG_FILE, raw)


def _clear_cron_job_id() -> None:
    """Remove cron_job_id from the skill config file."""
    conf = CONFIG_FILE
    if not conf.exists():
        return
    import re
    raw = read_file(conf)
    if "cron_job_id:" in raw:
        raw = re.sub(r"cron_job_id:.*\n?", "", raw)
        write_file(conf, raw)