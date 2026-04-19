#!/usr/bin/env python3
"""Convenience runner for project_insights.py.

Reads project_path, heartbeat_path, and project_language from config.md
so this script works generically for any adopted project.

Usage:
    python do_scan.py                       # refresh queue (default)
    python do_scan.py --clear               # clear non-user tasks
    python do_scan.py --detail "..."        # add item with detail
    python do_scan.py --lang en             # override language
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "scripts"))
from project_insights import refresh_queue, detect_project_type, clear_queue

SKILL_DIR = Path(__file__).parent
CONFIG_FILE = SKILL_DIR / "config.md"
DEFAULT_HEARTBEAT = SKILL_DIR / "HEARTBEAT.md"


def read_config() -> dict[str, str]:
    """Read key fields from config.md."""
    defaults = {
        "project_path": ".",
        "heartbeat_path": str(DEFAULT_HEARTBEAT),
        "project_language": "en",
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
    parser = argparse.ArgumentParser(description="Run project insights scan.")
    parser.add_argument(
        "--clear", action="store_true", help="Clear queue of all non-user entries"
    )
    parser.add_argument(
        "--detail", type=str, default=None, help="Detail text for new queue entries"
    )
    parser.add_argument(
        "--lang",
        type=str,
        default=None,
        choices=["en", "zh"],
        help="Override project_language from config.md",
    )
    args = parser.parse_args()

    config = read_config()
    project = Path(config["project_path"]).expanduser().resolve()
    heartbeat = Path(config["heartbeat_path"]).expanduser().resolve()
    lang = args.lang if args.lang else config["project_language"]

    if args.clear:
        removed = clear_queue(heartbeat)
        print(f"Do scan: cleared {removed} non-user entries")
        return 0

    ptype = detect_project_type(project)
    print(f"[project_insights] type={ptype} lang={lang}")
    added = refresh_queue(project, heartbeat, lang, min_items=5, detail=args.detail)
    print(f"Done. Added {added} items.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
