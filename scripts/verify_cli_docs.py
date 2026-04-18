#!/usr/bin/env python3
"""Verify that top-level CLI commands in a project appear in README examples.

This is a standalone, project-agnostic script. It:
1. Runs `<project>/.venv/bin/<cli-name> --help` to get CLI commands
2. Scans README.md for `health <cmd>` or `<cli-name> <cmd>` patterns
3. Reports mismatches (CLI has but README missing; README has but CLI missing)

Usage:
    python verify_cli_docs.py --project /path/to/project [--cli-name health] [--readme README.md]

Arguments:
    --project   Project root (required)
    --cli-name  CLI binary name (default: health)
    --readme    Path to README.md (default: <project>/README.md)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


def get_cli_commands(cli_bin: Path) -> set[str]:
    """Parse top-level subcommands from `cli-bin --help`."""
    result = subprocess.run(
        [str(cli_bin), "--help"],
        capture_output=True,
        text=True,
        check=True,
    )
    commands: set[str] = set()
    # Match: │ command_name  followed by 2+ spaces (description column)
    for line in result.stdout.splitlines():
        match = re.match(r"│ (\w+)\s{2,}", line)
        if match:
            cmd = match.group(1)
            if not cmd.startswith("-"):
                commands.add(cmd)
    return commands


def get_readme_commands(readme_path: Path, cli_name: str) -> set[str]:
    """Extract all `cli_name <cmd>` patterns from README.md."""
    content = readme_path.read_text(encoding="utf-8")
    commands: set[str] = set()
    # Match `cli_name word` or `cli_name word sub` in inline code or bullet lists
    pattern = re.compile(
        rf"(?:^|[`\s])({re.escape(cli_name)}\s+([a-zA-Z][\w-]*))",
        re.MULTILINE,
    )
    for match in pattern.finditer(content):
        commands.add(match.group(2))
    return commands


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify CLI commands are documented in README")
    parser.add_argument("--project", required=True, type=Path, help="Project root")
    parser.add_argument("--cli-name", default="health", help="CLI binary name (default: health)")
    parser.add_argument("--readme", type=Path, help="Path to README.md (default: <project>/README.md)")
    args = parser.parse_args()

    project = args.project.resolve()
    readme = (args.readme or (project / "README.md")).resolve()

    if not readme.exists():
        print(f"ERROR: README not found: {readme}", file=sys.stderr)
        return 1

    venv_bin = project / ".venv" / "bin"
    cli_bin = venv_bin / args.cli_name
    if not cli_bin.exists():
        print(f"ERROR: CLI binary not found: {cli_bin}", file=sys.stderr)
        return 1

    cli_commands = get_cli_commands(cli_bin)
    readme_commands = get_readme_commands(readme, args.cli_name)

    missing_in_readme = sorted(cli_commands - readme_commands)
    stale_in_readme = sorted(readme_commands - cli_commands)

    print("=" * 60)
    print(f"CLI commands:    {sorted(cli_commands)}")
    print(f"README commands: {sorted(readme_commands)}")
    print("=" * 60)

    if missing_in_readme:
        print(f"\n⚠️  CLI 有但 README 缺失 ({len(missing_in_readme)}):")
        for cmd in missing_in_readme:
            print(f"  - {args.cli_name} {cmd}")

    if stale_in_readme:
        print(f"\n⚠️  README 有但 CLI 缺失 ({len(stale_in_readme)}):")
        for cmd in stale_in_readme:
            print(f"  - {args.cli_name} {cmd}")

    if missing_in_readme or stale_in_readme:
        print("\n❌ CLI 文档校验失败")
        return 1

    print("\n✅ CLI 和 README 对齐")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
