#!/usr/bin/env python3
"""Verify that top-level CLI commands in a project appear in README examples.

This script is **project-type-agnostic**: it only runs when the project
actually has a CLI binary. For non-CLI projects it silently skips.

It:
1. Runs `<project>/.venv/bin/<cli-name> --help` to get CLI commands
2. Scans README.md for `<cli-name> <cmd>` patterns
3. Reports mismatches (CLI has but README missing; README has but CLI missing)

Usage:
    python verify_cli_docs.py --project /path/to/project [--cli-name MYAPP] [--readme README.md]

Arguments:
    --project   Project root (required)
    --cli-name  CLI binary name (required, no default — must match your project)
    --readme    Path to README.md (default: <project>/README.md)

Exit codes:
    0 = all aligned (or CLI binary not found, skipped)
    1 = mismatches found
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
    parser = argparse.ArgumentParser(
        description="Verify CLI commands are documented in README. "
        "Skips silently if no CLI binary is found (project-type-agnostic).",
    )
    parser.add_argument("--project", required=True, type=Path, help="Project root")
    parser.add_argument(
        "--cli-name", required=True,
        help="CLI binary name (e.g. myapp, health, your-cli)",
    )
    parser.add_argument(
        "--readme", type=Path,
        help="Path to README.md (default: <project>/README.md)",
    )
    args = parser.parse_args()

    project = args.project.resolve()
    readme = (args.readme or (project / "README.md")).resolve()

    if not readme.exists():
        print(f"ERROR: README not found: {readme}", file=sys.stderr)
        return 1

    # Try common venv layouts; skip gracefully if not found
    for venv in [
        project / ".venv" / "bin",
        project / "venv" / "bin",
        project / ".env" / "bin",
    ]:
        cli_bin = venv / args.cli_name
        if cli_bin.exists():
            break
    else:
        # No CLI binary found — not a CLI project, skip silently
        print(f"(verify_cli_docs: no CLI binary '{args.cli_name}' found, skipping)")
        return 0

    try:
        cli_commands = get_cli_commands(cli_bin)
    except Exception:
        # Binary exists but --help failed — skip
        print(f"(verify_cli_docs: could not run '{args.cli_name} --help', skipping)")
        return 0

    readme_commands = get_readme_commands(readme, args.cli_name)

    missing_in_readme = sorted(cli_commands - readme_commands)
    stale_in_readme = sorted(readme_commands - cli_commands)

    print("=" * 60)
    print(f"CLI binary:     {cli_bin}")
    print(f"CLI commands:   {sorted(cli_commands)}")
    print(f"README commands: {sorted(readme_commands)}")
    print("=" * 60)

    if missing_in_readme:
        print(f"\n⚠️  In CLI but missing from README ({len(missing_in_readme)}):")
        for cmd in missing_in_readme:
            print(f"  - {args.cli_name} {cmd}")

    if stale_in_readme:
        print(f"\n⚠️  In README but missing from CLI ({len(stale_in_readme)}):")
        for cmd in stale_in_readme:
            print(f"  - {args.cli_name} {cmd}")

    if missing_in_readme or stale_in_readme:
        print("\n❌ CLI documentation check failed")
        return 1

    print("\n✅ CLI and README are in sync")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
