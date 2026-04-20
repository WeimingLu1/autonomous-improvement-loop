#!/usr/bin/env python3
r"""
Bump the patch version in VERSION file.

Usage:
    bump_version.py [--path /path/to/project] [--commit]

    --path   Project root (default: cwd)
    --commit If set, also git add + commit VERSION (default: false)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def bump_version(project: Path, do_commit: bool = False, do_release: bool = False) -> str | None:
    version_file = project / "VERSION"
    if not version_file.exists():
        print(f"ERROR: VERSION not found at {version_file}", file=sys.stderr)
        return None
    try:
        old = version_file.read_text(encoding="utf-8").strip()
        parts = old.split(".")
        if len(parts) == 3:
            parts[2] = str(int(parts[2]) + 1)
            new_ver = ".".join(parts)
        else:
            new_ver = old + ".1"
        version_file.write_text(new_ver + "\n", encoding="utf-8")
        print(f"VERSION: {old} → {new_ver}")

        if do_commit:
            subprocess.run(["git", "add", "VERSION"], cwd=project, check=True)
            subprocess.run(
                ["git", "commit", "-m", f"chore: bump version to {new_ver}"],
                cwd=project,
                check=True,
            )
            print(f"VERSION commit created")

            if do_release:
                subprocess.run(["git", "push"], cwd=project, check=True)
                print(f"GitHub push done")
                subprocess.run(
                    ["gh", "release", "create", f"v{new_ver}",
                     "--title", f"v{new_ver}",
                     "--generate-notes"],
                    cwd=project,
                    check=True,
                )
                print(f"GitHub release v{new_ver} created")
        return new_ver
    except Exception as e:
        print(f"ERROR: failed to bump VERSION: {e}", file=sys.stderr)
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Bump patch version in VERSION file")
    parser.add_argument("--path", type=Path, default=Path.cwd())
    parser.add_argument("--commit", action="store_true",
                        help="Also git add + commit VERSION")
    parser.add_argument("--release", action="store_true",
                        help="Also git push + GitHub release (implies --commit")
    args = parser.parse_args()

    result = bump_version(args.path, do_commit=args.commit or args.release,
                          do_release=args.release)
    if result is None:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
