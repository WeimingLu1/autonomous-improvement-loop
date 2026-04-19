import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / 'scripts'))
from project_insights import refresh_queue, detect_project_type, clear_queue

project = Path('/Users/weiminglu/Projects/HealthAgent')
heartbeat = Path('/Users/weiminglu/.openclaw/workspace-viya/skills/autonomous-improvement-loop/HEARTBEAT.md')
lang = 'zh'
min_items = 5


def main() -> int:
    parser = argparse.ArgumentParser(description="Run project insights scan.")
    parser.add_argument("--clear", action="store_true", help="Clear queue of all non-user entries")
    parser.add_argument("--detail", type=str, default=None, help="Detail text for new queue entries")
    args = parser.parse_args()

    if args.clear:
        removed = clear_queue(heartbeat)
        print(f"Do scan: cleared {removed} non-user entries")
        return 0

    ptype = detect_project_type(project)
    print(f"[project_insights] type={ptype} lang={lang}")
    added = refresh_queue(project, heartbeat, lang, min_items, args.detail)
    print(f"Done. Added {added} items.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
