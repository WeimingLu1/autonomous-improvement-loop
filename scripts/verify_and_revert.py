#!/usr/bin/env python3
"""Verify task output and auto-revert on failure.

This script is TYPE-AGNOSTIC. It reads the project's verification command from
config.md and executes it. If the command fails, it reverts the last commit.
If no verification command is configured, it reports "unverified — manual check needed".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW IT WORKS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Run the configured verification command (from config.md → verification_command)
2. If it passes → report "pass"
3. If it fails → revert the commit and report "fail"
4. If no verification command is configured → report "unverified" and skip

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SUPPORTED PROJECT TYPES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

software  → e.g. pytest, npm test, cargo test, go test
writing    → e.g. readability-check, spell-check, consistency-review
video      → e.g. duration-check, script-review
research   → e.g. cite-check, spell-check, structure-review
generic    → any shell command, or empty for manual-only

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USAGE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  python verify_and_revert.py \
    --project /path/to/project \
    --commit <git-hash> \
    --task "description of what was done"
"""

from __future__ import annotations

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent


def read_config(project: Path) -> dict[str, str]:
    """Read key values from the skill's config.md."""
    config_path = SKILL_DIR / "config.md"
    if not config_path.exists():
        return {}
    result = {}
    for line in config_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if ':' not in line or line.startswith('#') or line.startswith('>'):
            continue
        key, _, value = line.partition(':')
        result[key.strip()] = value.strip()
    return result


def run(cmd: list[str], *, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=300)


def current_head(*, cwd: Path) -> str:
    return run(["git", "rev-parse", "HEAD"], cwd=cwd).stdout.strip()


def current_branch(*, cwd: Path) -> str:
    return run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd).stdout.strip()


def push(*, cwd: Path) -> None:
    result = run(["git", "push"], cwd=cwd)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)


def write_status(commit: str, result: str, task: str) -> None:
    print(f"[verify] status={result} commit={commit} task={task}")


def revert(start: str, end: str, *, cwd: Path) -> str:
    """Revert a range of commits (start..end) and push. Returns the new HEAD hash."""
    r = run(["git", "revert", "-n", f"{start}..{end}"], cwd=cwd)
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr, file=sys.stderr)
        raise SystemExit(r.returncode)
    r2 = run(["git", "commit", "--no-edit", "-m", f"Revert {start}..{end}"], cwd=cwd)
    if r2.returncode != 0:
        print(r2.stdout)
        print(r2.stderr, file=sys.stderr)
        raise SystemExit(r2.returncode)
    push(cwd=cwd)
    return run(["git", "rev-parse", "HEAD"], cwd=cwd).stdout.strip()


def run_verification(verify_cmd: str, *, cwd: Path) -> bool | None:
    """Run the verification command. Returns True/False/None (no command)."""
    if not verify_cmd.strip():
        return None
    parts = shlex.split(verify_cmd)
    print(f"[verify] running: {' '.join(parts)}")
    result = run(parts, cwd=cwd)
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify task output and auto-revert on failure. "
        "Type-agnostic: reads verification_command from config.md.",
    )
    parser.add_argument("--project", required=True, type=Path, help="Project root")
    parser.add_argument("--commit", required=True, help="Git hash before the task was done")
    parser.add_argument("--task", required=True, help="Task description")
    args = parser.parse_args()

    project = args.project.resolve()
    config = read_config(project)
    verify_cmd = config.get("verification_command", "").strip()

    head = current_head(cwd=project)
    if not head:
        print("ERROR: No commits in project — cannot verify or revert", file=sys.stderr)
        return 1
    branch = current_branch(cwd=project)
    print(f"[verify] project={project.name} branch={branch} commit={head}")
    print(f"[verify] task: {args.task}")

    push(cwd=project)

    result = run_verification(verify_cmd, cwd=project)

    if result is None:
        print("[verify] no verification_command configured — marking as unverified")
        write_status(head, "unverified", f"unverified: {args.task}")
        print("push done, no verification — manual check required")
        return 0

    if result is True:
        write_status(head, "pass", args.task)
        print("verification passed")
        return 0

    print("verification failed — reverting commit")
    reverted = revert(args.commit, head, cwd=project)
    write_status(reverted, "fail", f"rollback after failure: {args.task}")
    print(f"reverted, new HEAD={reverted}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
