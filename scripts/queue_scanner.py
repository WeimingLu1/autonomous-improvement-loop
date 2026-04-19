#!/usr/bin/env python3
"""Queue management wrapper for project_insights.py.

Provides queue operations (scan, clear) with project_insights.py as the backend.
Reads config.md for default project_path and heartbeat_path.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
SKILL_DIR = HERE.parent
CONFIG_FILE = SKILL_DIR / "config.md"


def _read_config() -> dict[str, str]:
    defaults = {
        "project_path": ".",
        "heartbeat_path": str(SKILL_DIR / "HEARTBEAT.md"),
    }
    if not CONFIG_FILE.exists():
        return defaults
    for line in CONFIG_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if ":" not in line or line.startswith("#"):
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if key in defaults:
            defaults[key] = value
    return defaults


def main() -> int:
    config = _read_config()
    default_project = Path(config["project_path"]).expanduser().resolve()
    default_heartbeat = Path(config["heartbeat_path"]).expanduser().resolve()

    parser = argparse.ArgumentParser(
        description="Queue management wrapper for project_insights.py. "
        "Supports --clear to remove non-user entries."
    )
    parser.add_argument("--clear", action="store_true", help="Clear queue of all non-user entries")
    parser.add_argument(
        "--project", type=Path, default=default_project,
        help=f"Project path (default: {default_project})"
    )
    parser.add_argument(
        "--heartbeat", type=Path, default=default_heartbeat,
        help=f"Heartbeat path (default: {default_heartbeat})"
    )
    parser.add_argument("--language", default="en", choices=["en", "zh"])
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--min", type=int, default=5)
    parser.add_argument("--detail", type=str, default=None, help="Detail text for new queue entries")
    args = parser.parse_args()

    cmd = [
        sys.executable, str(HERE / "project_insights.py"),
        "--project", str(args.project),
        "--heartbeat", str(args.heartbeat),
        "--language", args.language,
    ]
    if args.clear:
        cmd.append("--clear")
    if args.refresh:
        cmd.append("--refresh")
    if args.min != 5:
        cmd.extend(["--min", str(args.min)])
    if args.detail:
        cmd.extend(["--detail", args.detail])

    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    raise SystemExit(main())
