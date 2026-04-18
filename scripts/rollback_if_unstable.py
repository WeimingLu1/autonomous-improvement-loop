#!/usr/bin/env python3
"""Push HEAD, run pytest, and auto-rollback on failure.

This is a standalone, project-agnostic script. It:
1. Records current HEAD
2. Pushes to remote
3. Runs pytest via the project's venv
4. On pytest failure: git revert the current HEAD, push the revert, update Run Status with fail
5. On pytest success: update Run Status with pass

Usage:
    python rollback_if_unstable.py \
        --project /path/to/project \
        --heartbeat /path/to/HEARTBEAT.md \
        --task "<task description>" \
        [--cli-name health] \
        [--run-status-bin /path/to/run_status.py]

Arguments:
    --project        Project root (required)
    --heartbeat      Path to HEARTBEAT.md (required)
    --task           Task description for Run Status (required)
    --cli-name       CLI binary name (default: health)
    --run-status-bin Path to run_status.py (default: derived from this script's location)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], *, cwd: Path, check: bool = False) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if check and result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, cmd, result.stdout, result.stderr)
    return result


def current_head(*, cwd: Path) -> str:
    return run(["git", "rev-parse", "HEAD"], cwd=cwd, check=True).stdout.strip()


def current_branch(*, cwd: Path) -> str:
    return run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=cwd, check=True).stdout.strip()


def push(*, cwd: Path) -> None:
    result = run(["git", "push"], cwd=cwd)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        raise SystemExit(result.returncode)


def pytest_ok(pytest_bin: Path, *, cwd: Path) -> bool:
    result = run([str(pytest_bin), "-q"], cwd=cwd)
    if result.stdout:
        print(result.stdout)
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        return False
    return True


def update_status(
    run_status_bin: Path,
    heartbeat: Path,
    commit: str,
    result: str,
    task: str,
) -> None:
    status_proc = subprocess.run(
        [
            sys.executable,
            str(run_status_bin),
            "--heartbeat",
            str(heartbeat),
            "write",
            "--commit",
            commit,
            "--result",
            result,
            "--task",
            task,
        ],
        capture_output=True,
        text=True,
    )
    if status_proc.stdout:
        print(status_proc.stdout)
    if status_proc.returncode != 0:
        print(status_proc.stderr, file=sys.stderr)


def rollback(current_head: str, *, cwd: Path) -> str:
    """Revert the given commit and push. Returns the new HEAD hash."""
    revert = run(["git", "revert", "--no-edit", current_head], cwd=cwd)
    if revert.returncode != 0:
        print(revert.stdout)
        print(revert.stderr, file=sys.stderr)
        raise SystemExit(revert.returncode)
    push(cwd=cwd)
    return current_head(cwd=cwd)


def main() -> int:
    parser = argparse.ArgumentParser(description="Push, pytest, auto-rollback on failure")
    parser.add_argument("--project", required=True, type=Path, help="Project root")
    parser.add_argument("--heartbeat", required=True, type=Path, help="Path to HEARTBEAT.md")
    parser.add_argument("--task", required=True, help="Task description for Run Status")
    parser.add_argument(
        "--run-status-bin",
        type=Path,
        help="Path to run_status.py (default: scripts/run_status.py relative to this script)",
    )
    args = parser.parse_args()

    project = args.project.resolve()
    heartbeat = args.heartbeat.resolve()

    # Locate run_status.py: default to sibling scripts/run_status.py
    if args.run_status_bin:
        run_status_bin = args.run_status_bin.resolve()
    else:
        run_status_bin = Path(__file__).parent.resolve() / "run_status.py"

    pytest_bin = project / ".venv" / "bin" / "pytest"

    original_head = current_head(cwd=project)
    branch = current_branch(cwd=project)
    print(f"branch={branch} head={original_head}")

    push(cwd=project)

    if pytest_ok(pytest_bin, cwd=project):
        update_status(run_status_bin, heartbeat, original_head, "pass", args.task)
        print("✅ push 后 pytest 通过，无需回滚")
        return 0

    print("❌ push 后 pytest 失败，开始自动回滚")
    reverted_head = rollback(original_head, cwd=project)
    update_status(
        run_status_bin,
        heartbeat,
        reverted_head,
        "fail",
        f"rollback after failure: {args.task}",
    )
    print(f"✅ 已回滚，当前 HEAD={reverted_head}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
