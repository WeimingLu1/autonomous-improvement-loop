#!/usr/bin/env python3
"""Scan a project codebase for one concrete improvement candidate and append it
to the #feature queue in HEARTBEAT.md.

This is a standalone, project-agnostic script. It inspects src/, rules/, tests/
relative to the given --project path and appends exactly ONE new finding per run
to avoid flooding the queue.

Usage:
    python queue_scanner.py \
        --project /path/to/project \
        --heartbeat /path/to/HEARTBEAT.md \
        [--repo https://github.com/OWNER/REPO]

Arguments:
    --project   Project root (required)
    --heartbeat Path to HEARTBEAT.md (required)
    --repo      GitHub repo URL for issue links (default: https://github.com/OWNER/REPO)
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HEARTBEAT_TEMPLATE = "https://github.com/OWNER/REPO"


def now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def existing_heartbeat(heartbeat: Path) -> str:
    return normalize(heartbeat.read_text(encoding="utf-8"))


def _relative(py_file: Path, root: Path) -> str:
    try:
        return str(py_file.relative_to(root))
    except ValueError:
        return str(py_file)


# ── Scan buckets (each returns a list of finding strings) ────────────────────

def rule_test_gaps(project: Path) -> list[str]:
    """Rules in rules/ that have no corresponding test file in tests/test_rules/."""
    findings: list[str] = []
    rules_dir = project / "rules"
    tests_dir = project / "tests"
    if not rules_dir.is_dir():
        return findings
    for py_file in sorted(rules_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        expected = tests_dir / "test_rules" / f"test_{py_file.stem}.py"
        if not expected.exists():
            findings.append(f"补齐 {py_file.name} 的单元测试（tests/test_rules/test_{py_file.stem}.py）")
    return findings


def todo_findings(project: Path) -> list[str]:
    """TODO/FIXME/HACK comments in src/."""
    findings: list[str] = []
    src_dir = project / "src"
    if not src_dir.is_dir():
        return findings
    for py_file in sorted(src_dir.rglob("*.py")):
        if "__pycache__" in str(py_file):
            continue
        for line_no, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\b(TODO|FIXME|HACK|XXX)\b", line, re.IGNORECASE):
                findings.append(f"处理 {_relative(py_file, project)}:{line_no} 的待办注释")
    return findings


def missing_docstrings(project: Path) -> list[str]:
    """Python files in src/ that lack a module-level docstring."""
    findings: list[str] = []
    src_dir = project / "src"
    if not src_dir.is_dir():
        return findings
    for py_file in sorted(src_dir.rglob("*.py")):
        if "__pycache__" in str(py_file) or py_file.name.startswith("_"):
            continue
        head = py_file.read_text(encoding="utf-8")[:300]
        if '"""' not in head and "'''" not in head:
            findings.append(f"为 {_relative(py_file, project)} 补齐模块 docstring")
    return findings


def cli_json_gaps(project: Path) -> list[str]:
    """CLI modules that lack a --json option."""
    findings: list[str] = []
    cli_dir = project / "cli"
    if not cli_dir.is_dir():
        return findings
    for py_file in sorted(cli_dir.glob("*.py")):
        if py_file.stem in {"__init__", "__main__", "main"}:
            continue
        content = py_file.read_text(encoding="utf-8")
        if '"--json"' not in content and "'--json'" not in content:
            findings.append(f"为 cli/{py_file.stem} 增加 --json 输出支持")
    return findings


def service_test_gaps(project: Path) -> list[str]:
    """Service files in services/ that have no corresponding test in tests/test_services/."""
    findings: list[str] = []
    services_dir = project / "services"
    tests_dir = project / "tests"
    if not services_dir.is_dir():
        return findings
    for py_file in sorted(services_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        expected = tests_dir / "test_services" / f"test_{py_file.stem}.py"
        if not expected.exists():
            findings.append(f"补齐 services/{py_file.stem} 的单元测试（tests/test_services/test_{py_file.stem}.py）")
    return findings


# ── Core logic ────────────────────────────────────────────────────────────────

def choose_candidate(project: Path, heartbeat: Path) -> str | None:
    """Pick the first new finding from priority buckets, skipping duplicates."""
    existing = existing_heartbeat(heartbeat)
    for bucket in (
        rule_test_gaps(project),
        service_test_gaps(project),
        todo_findings(project),
        missing_docstrings(project),
        cli_json_gaps(project),
    ):
        for finding in bucket:
            if normalize(finding) not in existing:
                return finding
    return None


def append_candidate(heartbeat: Path, repo: str, finding: str) -> bool:
    """Append one numbered entry to the Queue section of HEARTBEAT.md."""
    content = heartbeat.read_text(encoding="utf-8")

    # Find the Queue section: starts with "## Queue\n\n", ends at next ## section
    section_match = re.search(r"(## Queue\n\n)([\s\S]*?)(\n---\n)", content)
    if not section_match:
        print("ERROR: Queue section not found in HEARTBEAT.md", file=sys.stderr)
        return False

    # Call priority_scorer.py to get a score for this finding
    scorer = Path(__file__).parent / "priority_scorer.py"
    score = 50  # default
    if scorer.exists():
        try:
            result = subprocess.run(
                [sys.executable, str(scorer), "--task", finding, "--type", "improve"],
                capture_output=True, text=True, timeout=30,
            )
            fallback_match = re.search(r'# 规则 fallback 评分.*?\n(.+)', result.stdout, re.DOTALL)
            if fallback_match:
                fallback = json.loads(fallback_match.group(1))
                score = fallback.get("score", 50)
        except Exception:
            pass  # keep default score 50

    section_body = section_match.group(2)
    # Extract numbers from table rows: | # | ... → capture the # cell
    numbers = [int(m) for m in re.findall(r"^\|\s*(\d+)\s+\|", section_body, re.MULTILINE)]
    next_num = max(numbers) + 1 if numbers else 1

    new_line = f"{next_num}. [[Improve]] score={score} | {finding} | scanner | pending | {now_str()}"
    new_section = section_match.group(1) + section_body.rstrip() + "\n" + new_line + "\n" + section_match.group(3)
    updated = content[:section_match.start()] + new_section + content[section_match.end():]
    heartbeat.write_text(updated, encoding="utf-8")
    print(f"queue_scanner: appended -> {new_line}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan project and append one improvement to HEARTBEAT.md")
    parser.add_argument("--project", required=True, type=Path, help="Project root directory")
    parser.add_argument("--heartbeat", required=True, type=Path, help="Path to HEARTBEAT.md")
    parser.add_argument("--repo", default=HEARTBEAT_TEMPLATE, help="GitHub repo for issue links")
    args = parser.parse_args()

    candidate = choose_candidate(args.project, args.heartbeat)
    if not candidate:
        print("queue_scanner: no new improvement candidate found")
        return 0
    return 0 if append_candidate(args.heartbeat, args.repo, candidate) else 1


if __name__ == "__main__":
    raise SystemExit(main())
