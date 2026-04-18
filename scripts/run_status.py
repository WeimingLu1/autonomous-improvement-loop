#!/usr/bin/env python3
"""Read or write the Run Status block in a HEARTBEAT.md file.

This is a standalone, project-agnostic script — it knows nothing about any
specific project. It only manages the Run Status table in HEARTBEAT.md.

Usage:
    python run_status.py --heartbeat /path/to/HEARTBEAT.md read
    python run_status.py --heartbeat /path/to/HEARTBEAT.md write \
        --commit <hash> --result pass|fail --task "<task desc>"
    python run_status.py --heartbeat /path/to/HEARTBEAT.md write \
        --commit <hash> --result pass --task "<task>" --mode bootstrap
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

BLOCK_RE = re.compile(r"## Run Status\n\n>[\s\S]*?\n---\n", re.MULTILINE)


def now_shanghai() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S CST")


def render_block(
    last_run_time: str,
    last_run_commit: str,
    last_run_result: str,
    last_run_task: str,
    cron_lock: str = "false",
    mode: str = "normal",
) -> str:
    return (
        "## Run Status\n\n"
        "> Managed by autonomous-improvement-loop skill scripts. Do not edit manually.\n\n"
        "| Field | Value |\n"
        "|-------|-------|\n"
        f"| last_run_time | {last_run_time} |\n"
        f"| last_run_commit | `{last_run_commit}` |\n"
        f"| last_run_result | {last_run_result} |\n"
        f"| last_run_task | {last_run_task} |\n"
        f"| cron_lock | {cron_lock} |\n"
        f"| mode | {mode} |\n"
        "| rollback_on_fail | true |\n\n"
        "---\n"
    )


def extract_status(content: str) -> dict[str, str]:
    defaults = {
        "last_run_time": "never",
        "last_run_commit": "none",
        "last_run_result": "unknown",
        "last_run_task": "none",
        "cron_lock": "false",
        "mode": "normal",
    }
    patterns = {
        "last_run_time": r"\| last_run_time \|\s*(.+?)\s*\|",
        "last_run_commit": r"\| last_run_commit \|\s*`(.+?)`\s*\|",
        "last_run_result": r"\| last_run_result \|\s*(.+?)\s*\|",
        "last_run_task": r"\| last_run_task \|\s*(.+?)\s*\|",
        "cron_lock": r"\| cron_lock \|\s*(.+?)\s*\|",
        "mode": r"\| mode \|\s*(.+?)\s*\|",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, content)
        if match:
            defaults[key] = match.group(1).strip()
    return defaults


def ensure_block(content: str) -> str:
    if "## Run Status" in content:
        return content
    insert_after = content.find("---\n")
    if insert_after == -1:
        return render_block("never", "none", "unknown", "none", "false", "normal") + "\n" + content
    insert_after += len("---\n")
    return content[:insert_after] + "\n" + render_block("never", "none", "unknown", "none", "false", "normal") + "\n" + content[insert_after:]


def read_status(heartbeat: Path) -> dict[str, str]:
    content = ensure_block(heartbeat.read_text(encoding="utf-8"))
    status = extract_status(content)
    for key, value in status.items():
        print(f"{key}={value}")
    return status


def write_status(
    heartbeat: Path,
    commit: str,
    result: str,
    task: str,
    cron_lock: str = "unchanged",
    mode: str = "unchanged",
) -> None:
    content = ensure_block(heartbeat.read_text(encoding="utf-8"))
    status = extract_status(content)
    current_cron_lock = status.get("cron_lock", "false")
    resolved_cron_lock = current_cron_lock if cron_lock == "unchanged" else cron_lock
    current_mode = status.get("mode", "normal")
    resolved_mode = current_mode if mode == "unchanged" else mode
    new_block = render_block(
        now_shanghai(), commit, result, task, resolved_cron_lock, resolved_mode
    )
    updated = (
        BLOCK_RE.sub(new_block, content, count=1)
        if BLOCK_RE.search(content)
        else new_block + "\n" + content
    )
    heartbeat.write_text(updated, encoding="utf-8")
    print(f"Run Status updated: commit={commit} result={result} mode={resolved_mode}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read or write Run Status in HEARTBEAT.md"
    )
    parser.add_argument("--heartbeat", required=True, type=Path, help="Path to HEARTBEAT.md")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("read")
    write_parser = subparsers.add_parser("write")
    write_parser.add_argument("--commit", required=True)
    write_parser.add_argument("--result", required=True, choices=["pass", "fail"])
    write_parser.add_argument("--task", required=True)
    write_parser.add_argument("--cron-lock", choices=["true", "false"])
    write_parser.add_argument("--mode", choices=["bootstrap", "normal"])

    args = parser.parse_args()
    if args.command == "read":
        read_status(args.heartbeat)
    elif args.command == "write":
        write_status(
            args.heartbeat,
            args.commit,
            args.result,
            args.task,
            getattr(args, "cron_lock", "unchanged"),
            getattr(args, "mode", "unchanged"),
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
