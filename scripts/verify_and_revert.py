#!/usr/bin/env python3
"""Verify task output and auto-revert on failure.

This script is TYPE-AGNOSTIC. It reads the project's verification command from
config.md and executes it. If the command fails, it reverts the last commit.
If no verification command is configured, it reports "unverified — manual check needed".

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
HOW IT WORKS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. Run the configured verification command (from config.md → verification_command)
2. If it passes → write "pass" to Run Status
3. If it fails → revert the commit, write "fail" to Run Status
4. If no verification command is configured → write "unverified" and skip

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
    --heartbeat /path/to/HEARTBEAT.md \
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


def read_config(heartbeat: Path) -> dict[str, str]:
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
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)


def current_head(*, cwd: Path) -> str:
    return run(["git", "rev-parse", "HEAD"], cwd=cwd).stdout.strip()


def current_branch(*, cwd: Path) -> str:
    return run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd).stdout.strip()


def push(*, cwd: Path) -> None:
    result = run(["git", "push"], cwd=cwd)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)


def write_status(
    heartbeat: Path,
    commit: str,
    result: str,
    task: str,
) -> None:
    run_status_bin = Path(__file__).parent / "run_status.py"
    cmd = [
        sys.executable,
        str(run_status_bin),
        "--heartbeat", str(heartbeat),
        "write",
        "--commit", commit,
        "--result", result,
        "--task", task,
    ]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.stdout:
        print(r.stdout)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)


def revert(commit_to_revert: str, *, cwd: Path) -> str:
    """Revert the given commit and push. Returns the new HEAD hash."""
    r = run(["git", "revert", "--no-edit", commit_to_revert], cwd=cwd)
    if r.returncode != 0:
        print(r.stdout)
        print(r.stderr, file=sys.stderr)
        raise SystemExit(r.returncode)
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
    parser.add_argument("--heartbeat", required=True, type=Path, help="Path to HEARTBEAT.md")
    parser.add_argument("--commit", required=True, help="Git hash before the task was done")
    parser.add_argument("--task", required=True, help="Task description")
    args = parser.parse_args()

    project = args.project.resolve()
    heartbeat = args.heartbeat.resolve()

    config = read_config(heartbeat)
    verify_cmd = config.get("verification_command", "").strip()

    head = current_head(cwd=project)
    branch = current_branch(cwd=project)
    print(f"[verify] project={project.name} branch={branch} commit={head}")
    print(f"[verify] task: {args.task}")

    push(cwd=project)

    result = run_verification(verify_cmd, cwd=project)

    if result is None:
        print("[verify] no verification_command configured — marking as unverified")
        write_status(heartbeat, head, "unverified", f"unverified: {args.task}")
        print("push done, no verification — manual check required")
        return 0

    if result is True:
        write_status(heartbeat, head, "pass", args.task)
        print("verification passed")
        return 0

    print("verification failed — reverting commit")
    reverted = revert(args.commit, cwd=project)
    write_status(heartbeat, reverted, "fail", f"rollback after failure: {args.task}")
    print(f"reverted, new HEAD={reverted}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
