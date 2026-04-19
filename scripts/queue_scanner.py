#!/usr/bin/env python3
"""Queue management wrapper for project_insights.py.

Provides queue operations (scan, clear) with project_insights.py as the backend.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Queue management wrapper for project_insights.py. "
        "Supports --clear to remove non-user entries."
    )
    parser.add_argument("--clear", action="store_true", help="Clear queue of all non-user entries")
    parser.add_argument("--project", type=Path, help="Project path (passed to project_insights.py)")
    parser.add_argument("--heartbeat", type=Path, help="Heartbeat path (passed to project_insights.py)")
    parser.add_argument("--language", default="en", choices=["en", "zh"])
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--min", type=int, default=5)
    parser.add_argument("--detail", type=str, default=None, help="Detail text for new queue entries")
    args = parser.parse_args()

    # Forward all args to project_insights.py via subprocess
    cmd = [sys.executable, str(HERE / "project_insights.py")]
    if args.clear:
        cmd.append("--clear")
    if args.project:
        cmd.extend(["--project", str(args.project)])
    if args.heartbeat:
        cmd.extend(["--heartbeat", str(args.heartbeat)])
    cmd.extend(["--language", args.language])
    if args.refresh:
        cmd.append("--refresh")
    if args.min != 5:
        cmd.extend(["--min", str(args.min)])
    if args.detail:
        cmd.extend(["--detail", args.detail])

    return subprocess.run(cmd).returncode


if __name__ == "__main__":
    raise SystemExit(main())
