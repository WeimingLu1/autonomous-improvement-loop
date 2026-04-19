#!/usr/bin/env python3
r"""
Post-task HEARTBEAT update script.

Called by the cron agent after task execution to reliably update HEARTBEAT.md
instead of relying on manual file edits. Performs:
  1. Mark the specified (or first pending) task as done
  2. Append Done Log entry
  3. Update Run Status fields
  4. Refresh the queue (clear stale non-user + scan new items)
  5. Release cron_lock

Usage:
  update_heartbeat.py --heartbeat HEARTBEAT.md \
      --project /path/to/project \
      --commit abc1234 \
      --result pass \
      --task "Did the thing" \
      [--task-num 3]        # specific queue row to mark done
      [--min-queue 5]        # min items after refresh (default: 5)
      [--language zh]        # project language (default: en)
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).parent.resolve()
SKILL_DIR = HERE.parent


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _strip_prefix(content: str) -> str:
    content = re.sub(r"^\[\[[^\]]+\]\]\s*score=\d+\s*\|\s*", "", content).strip()
    content = re.sub(r"^\[\[[^\]]+\]\]\s*", "", content).strip()
    return content


def _parse_all_queue_rows(content: str) -> list[dict[str, str]]:
    """Parse ALL queue rows from ALL ## Queue sections."""
    rows: list[dict[str, str]] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or "---" in stripped or stripped.startswith("| #"):
            continue
        cells = [c.strip() for c in stripped.split("|")[1:-1]]
        if not cells or not re.match(r"^\d+$", cells[0]):
            continue
        if len(cells) >= 8:
            rows.append({
                "num": cells[0], "type": cells[1], "score": cells[2],
                "content": cells[3], "detail": cells[4],
                "source": cells[5], "status": cells[6], "created": cells[7],
            })
        elif len(cells) >= 7:
            rows.append({
                "num": cells[0], "type": cells[1], "score": cells[2],
                "content": cells[3], "detail": cells[3],
                "source": cells[4], "status": cells[5], "created": cells[6],
            })
    return rows


def _render_queue_block(rows: list[dict[str, str]]) -> str:
    table_lines = [
        "| # | Type | Score | Content | Detail | Source | Status | Created |",
        "|---|------|-------|---------|--------|--------|--------|--------|",
    ]
    for idx, row in enumerate(rows, 1):
        table_lines.append(
            f"| {idx} | {row['type']} | {row['score']} | {row['content']} | {row['detail']} | {row['source']} | {row['status']} | {row['created']} |"
        )
    return "## Queue\n\n" + "\n".join(table_lines) + "\n\n---\n"


def _replace_all_queue_sections(content: str, new_block: str) -> str:
    """Replace every ## Queue section with a single freshly rendered block."""
    lines = content.splitlines(keepends=True)
    kept: list[str] = []
    i = 0
    while i < len(lines):
        if "## Queue" in lines[i]:
            i += 1
            while i < len(lines) and lines[i].strip() != "---":
                i += 1
            if i < len(lines) and lines[i].strip() == "---":
                i += 1
            while i < len(lines) and lines[i].strip() == "":
                i += 1
            continue
        kept.append(lines[i])
        i += 1

    stripped_content = "".join(kept)
    run_status_match = re.search(r"\n## Run Status\n", stripped_content)
    if run_status_match:
        insert_at = run_status_match.start()
        return stripped_content[:insert_at] + new_block + stripped_content[insert_at:]
    dash_match = re.search(r"\n---\n", stripped_content)
    if dash_match:
        return stripped_content[:dash_match.start()] + new_block + stripped_content[dash_match.start():]
    return new_block + stripped_content


def _update_heartbeat(
    heartbeat: Path,
    project: Path,
    *,
    commit: str,
    result: str,
    task: str,
    task_num: int | None,
    min_queue: int,
    language: str,
) -> None:
    """Perform all post-task HEARTBEAT updates atomically."""
    content = heartbeat.read_text(encoding="utf-8")
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # ── 1. Mark target task as done ──────────────────────────────────────────
    all_rows = _parse_all_queue_rows(content)
    if not all_rows:
        print("WARNING: no queue rows found", file=sys.stderr)

    # Find target row
    target_idx: int | None = None
    if task_num is not None:
        for i, row in enumerate(all_rows):
            if row["num"] == str(task_num) and row["status"].lower() == "pending":
                target_idx = i
                break
    if target_idx is None:
        # Default: first pending row
        for i, row in enumerate(all_rows):
            if row["status"].lower() == "pending":
                target_idx = i
                break

    if target_idx is not None:
        all_rows[target_idx]["status"] = "done" if result == "pass" else "skip"
        print(
            f"Marked row {all_rows[target_idx]['num']} as {all_rows[target_idx]['status']}: "
            f"{all_rows[target_idx]['content'][:50]}"
        )
    else:
        print("No pending task found to mark as done")

    new_block = _render_queue_block(all_rows)
    content = _replace_all_queue_sections(content, new_block)

    # ── 2. Append Done Log entry ─────────────────────────────────────────────
    done_entry = f"| {ts} | {commit} | {task} | {result} |\n"
    dl_match = re.search(r"(\n## Done Log\n\n\| Time \|[^\n]+\n)(\|[^\n]+\n)", content)
    if dl_match:
        content = content[:dl_match.end()] + done_entry + content[dl_match.end():]
    else:
        print("WARNING: Done Log section not found, appending after Run Status", file=sys.stderr)
        rs_match = re.search(r"(\n## Run Status\n)", content)
        if rs_match:
            content = content[:rs_match.start()] + "\n## Done Log\n\n| Time | Commit | Task | Result |\n|------|--------|------|--------|\n" + done_entry + content[rs_match.start():]

    # ── 3. Update Run Status ─────────────────────────────────────────────────
    content = re.sub(
        r"(\| last_run_time \|) [^|]+ (\|)",
        f"\\1 {ts} \\2", content
    )
    content = re.sub(
        r"(\| last_run_commit \|) [^|]+ (\|)",
        f"\\1 {commit} \\2", content
    )
    content = re.sub(
        r"(\| last_run_result \|) [^|]+ (\|)",
        f"\\1 {result} \\2", content
    )
    content = re.sub(
        r"(\| last_run_task \|) [^\|]+ (\|)",
        f"\\1 {task} \\2", content
    )
    content = re.sub(
        r"(\| cron_lock \|) [^|]+ (\|)",
        r"\1 false \2", content
    )

    heartbeat.write_text(content, encoding="utf-8")
    print(f"Run Status updated, cron_lock released")

    # ── 4. Refresh queue (clear stale non-user + scan new items) ────────────
    # Import and run project_insights
    sys.path.insert(0, str(HERE))
    try:
        import project_insights as pi
    except Exception as e:
        print(f"WARNING: could not import project_insights: {e}", file=sys.stderr)
        return

    project = project.expanduser().resolve()
    heartbeat_p = heartbeat

    # Clear non-user rows
    try:
        removed = pi.clear_queue(heartbeat_p)
        print(f"Queue cleared: {removed} non-user row(s) removed")
    except Exception as e:
        print(f"WARNING: clear_queue failed: {e}", file=sys.stderr)

    # Refresh with new candidates
    try:
        added = pi.refresh_queue(project, heartbeat_p, language, min_queue)
        print(f"Queue refreshed: {added} new item(s) added")
    except Exception as e:
        print(f"WARNING: refresh_queue failed: {e}", file=sys.stderr)

    # ── 5. Done ──────────────────────────────────────────────────────────────
    print(f"\nHEARTBEAT update complete: {ts}")


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Post-task HEARTBEAT updater for Autonomous Improvement Loop. "
        "Automatically marks task done, appends Done Log, refreshes queue, "
        "and releases cron_lock."
    )
    parser.add_argument("--heartbeat", required=True, type=Path,
                        help="Path to HEARTBEAT.md")
    parser.add_argument("--project", required=True, type=Path,
                        help="Path to the project being improved")
    parser.add_argument("--commit", required=True,
                        help="Git commit hash of the completed task")
    parser.add_argument("--result", required=True, choices=["pass", "fail", "skip"],
                        help="Task result")
    parser.add_argument("--task", required=True,
                        help="Task description (for Done Log)")
    parser.add_argument("--task-num", type=int, default=None,
                        help="Queue row number to mark done (default: first pending)")
    parser.add_argument("--min-queue", type=int, default=5,
                        help="Minimum queue items after refresh (default: 5)")
    parser.add_argument("--language", default="en", choices=["en", "zh"],
                        help="Project/output language (default: en)")

    args = parser.parse_args()

    if not args.heartbeat.exists():
        print(f"ERROR: HEARTBEAT not found: {args.heartbeat}", file=sys.stderr)
        return 1

    try:
        _update_heartbeat(
            heartbeat=args.heartbeat,
            project=args.project,
            commit=args.commit,
            result=args.result,
            task=args.task,
            task_num=args.task_num,
            min_queue=args.min_queue,
            language=args.language,
        )
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
