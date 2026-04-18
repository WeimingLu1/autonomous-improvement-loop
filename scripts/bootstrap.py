#!/usr/bin/env python3
"""Bootstrap a project for the Autonomous Improvement Loop.

This script handles two scenarios:

  1. NEW PROJECT -- generates a bootstrap queue to make the project AI-ready
  2. EXISTING PROJECT -- scans the codebase and populates HEARTBEAT.md with
     detected improvement opportunities

Usage:
    python bootstrap.py --project ~/Projects/MY_PROJECT --skill-dir ~/.openclaw/workspace-YOUR_AGENT/skills/autonomous-improvement-loop --mode new
    python bootstrap.py --project ~/Projects/MY_PROJECT --skill-dir ~/.openclaw/workspace-YOUR_AGENT/skills/autonomous-improvement-loop --mode existing
    python bootstrap.py --project ~/Projects/MY_PROJECT --skill-dir ~/.openclaw/workspace-YOUR_AGENT/skills/autonomous-improvement-loop --mode detect

The script detects the project state automatically if --mode is omitted.

---

**LEGACY / PYTHON-ONLY NOTE:**
This helper is kept for backward compatibility with Python software projects
onboarded before v6. It is Python-specific and does NOT support writing, video,
or research project types.
For all new projects and non-Python projects, use `init.py adopt` instead.
This script may be removed in a future version.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# ---------------------------------------------------------------------------
# Project readiness checks
# ---------------------------------------------------------------------------


def check_readiness(project_path: Path) -> dict:
    """Run all readiness checks and return a dict of check -> result."""
    results = {}

    # VERSION file
    version_file = project_path / "VERSION"
    results["VERSION exists"] = version_file.exists()

    # Git repo
    results["Git repo"] = (project_path / ".git").exists()

    # Python project structure
    results["src/ directory"] = (project_path / "src").exists()
    results["tests/ directory"] = (project_path / "tests").exists()

    # Pytest available
    try:
        r = subprocess.run(
            ["python3", "-m", "pytest", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        results["pytest available"] = r.returncode == 0
    except Exception:
        results["pytest available"] = False

    # README
    results["README exists"] = any(
        (project_path / f"README{i}").exists()
        for i in ["", ".md", ".rst"]
    )

    # Package manager
    results["pyproject.toml or setup.py"] = any(
        (project_path / f).exists()
        for f in ["pyproject.toml", "setup.py", "setup.cfg"]
    )

    return results


def is_new_project(project_path: Path) -> bool:
    """Return True if this looks like a brand-new project (no VERSION, no real src)."""
    checks = check_readiness(project_path)
    score = sum(1 for v in checks.values() if v)
    # New project: 0-2 checks pass
    return score <= 2


# ---------------------------------------------------------------------------
# Bootstrap queue for new projects
# ---------------------------------------------------------------------------


PYTHON_NEW_PROJECT_BOOTSTRAP = [
    {
        "type": "feature",
        "score": 100,
        "content": "[[Bootstrap]] Initialize project structure: src/, tests/, docs/ directories",
        "source": "bootstrap",
        "note": "Create the minimum directory structure the project needs",
    },
    {
        "type": "feature",
        "score": 100,
        "content": "[[Bootstrap]] Add pyproject.toml with project metadata and pytest config",
        "source": "bootstrap",
        "note": "Enable dependency management and test running",
    },
    {
        "type": "feature",
        "score": 90,
        "content": "[[Bootstrap]] Create VERSION file (e.g. 0.0.1)",
        "source": "bootstrap",
        "note": "AI needs version tracking to create releases",
    },
    {
        "type": "feature",
        "score": 90,
        "content": "[[Bootstrap]] Write first passing test in tests/",
        "source": "bootstrap",
        "note": "AI needs tests to validate changes — even a simple smoke test counts",
    },
    {
        "type": "feature",
        "score": 80,
        "content": "[[Bootstrap]] Create README.md with install/use instructions",
        "source": "bootstrap",
        "note": "Basic user-facing documentation",
    },
    {
        "type": "feature",
        "score": 70,
        "content": "[[Bootstrap]] Initialize git repo and first commit",
        "source": "bootstrap",
        "note": "AI needs git history to create releases",
    },
    {
        "type": "feature",
        "score": 60,
        "content": "[[Bootstrap]] Connect to GitHub repo (gh repo create / push)",
        "source": "bootstrap",
        "note": "AI uses GitHub for releases and code review",
    },
    {
        "type": "feature",
        "score": 50,
        "content": "[[Bootstrap]] Add CI workflow (.github/workflows/ci.yml)",
        "source": "bootstrap",
        "note": "Automated test running on every push",
    },
]

GENERIC_NEW_PROJECT_BOOTSTRAP = [
    {
        "type": "feature",
        "score": 100,
        "content": "[[Bootstrap]] Set up project directory structure",
        "source": "bootstrap",
        "note": "Create src/, tests/, docs/ as needed",
    },
    {
        "type": "feature",
        "score": 100,
        "content": "[[Bootstrap]] Create VERSION file (e.g. 0.0.1)",
        "source": "bootstrap",
        "note": "AI needs version tracking to create releases",
    },
    {
        "type": "feature",
        "score": 90,
        "content": "[[Bootstrap]] Initialize git repo and connect to GitHub",
        "source": "bootstrap",
        "note": "AI uses git + GitHub for all releases",
    },
    {
        "type": "feature",
        "score": 90,
        "content": "[[Bootstrap]] Write first passing test",
        "source": "bootstrap",
        "note": "AI needs a passing test suite before it can safely make changes",
    },
    {
        "type": "feature",
        "score": 80,
        "content": "[[Bootstrap]] Create README with install/use instructions",
        "source": "bootstrap",
        "note": "Basic user-facing documentation",
    },
    {
        "type": "feature",
        "score": 70,
        "content": "[[Bootstrap]] Add CI/CD workflow for automated testing",
        "source": "bootstrap",
        "note": "Automated test running on every push",
    },
]


# ---------------------------------------------------------------------------
# Existing project scanner
# ---------------------------------------------------------------------------

def detect_language(project_path: Path) -> str:
    """Detect the primary language of the project."""
    extensions = {}
    for p in project_path.rglob("*"):
        if p.is_file() and not any(
            part.startswith(".") or part in {"node_modules", "__pycache__", "venv", ".venv"}
            for part in p.parts
        ):
            ext = p.suffix.lower()
            if ext in (".py", ".js", ".ts", ".go", ".rs", ".java", ".rb", ".php", ".c", ".cpp", ".h"):
                extensions[ext] = extensions.get(ext, 0) + 1
    if not extensions:
        return "unknown"
    return max(extensions, key=extensions.get)


def scan_existing_project(project_path: Path) -> list[dict]:
    """Scan an existing project and generate initial queue items."""
    items = []
    lang = detect_language(project_path)

    # Check for TODO/FIXME comments
    todo_pattern = re.compile(r"#\s*(TODO|FIXME|HACK|XXX|NOTE):\s*(.+)", re.IGNORECASE)
    found_todos = []
    for p in project_path.rglob("*"):
        if p.is_file() and p.suffix.lower() in (".py", ".js", ".ts", ".go", ".rs", ".java", ".rb", ".md"):
            if any(x in p.parts for x in ["node_modules", "__pycache__", ".venv", "venv"]):
                continue
            try:
                for lineno, line in enumerate(p.read_text(encoding="utf-8", errors="ignore").splitlines(), 1):
                    for m in todo_pattern.finditer(line):
                        found_todos.append({
                            "content": f"[[Improve]] {m.group(2).strip()[:120]} (from {p.name}:{lineno})",
                            "source": "scanner:TODO",
                            "score": 50,
                            "type": "improve",
                        })
            except Exception:
                pass

    # Check for missing tests
    test_dirs = list(project_path.rglob("tests"))
    src_dirs = list(project_path.rglob("src"))
    if not test_dirs and src_dirs:
        items.append({
            "type": "improve",
            "score": 65,
            "content": "[[Improve]] Add test suite (no tests/ directory detected)",
            "source": "scanner:structure",
        })

    # Check for missing README
    has_readme = any((project_path / f"README{i}").exists() for i in ["", ".md", ".rst"])
    if not has_readme:
        items.append({
            "type": "feature",
            "score": 70,
            "content": "[[Improve]] Create README.md with install and usage instructions",
            "source": "scanner:structure",
        })

    # Check for missing VERSION
    if not (project_path / "VERSION").exists():
        items.append({
            "type": "feature",
            "score": 85,
            "content": "[[Improve]] Add VERSION file for release tracking",
            "source": "scanner:structure",
        })

    # Language-specific items
    if lang == ".py":
        items.append({
            "type": "improve",
            "score": 50,
            "content": "[[Improve]] Add type hints to modules without them",
            "source": "scanner:structure",
        })
        items.append({
            "type": "improve",
            "score": 50,
            "content": "[[Improve]] Run pytest -q and fix any failing tests",
            "source": "scanner:structure",
        })

    # GitHub issues (if gh is available)
    try:
        r = subprocess.run(
            ["gh", "issue", "list", "--state", "open", "--limit", "10", "--json", "title,labels"],
            capture_output=True, text=True, timeout=15
        )
        if r.returncode == 0:
            issues = json.loads(r.stdout)
            for issue in issues[:5]:
                label_names = [l.get("name","") for l in issue.get("labels", [])]
                is_bug = any("bug" in l.lower() for l in label_names)
                items.append({
                    "type": "bug" if is_bug else "feature",
                    "score": 88 if is_bug else 65,
                    "content": f"[[{'Bug' if is_bug else 'Feature'}]] {issue['title']} (GitHub Issue)",
                    "source": "scanner:github-issue",
                })
    except Exception:
        pass  # gh not available or no repo

    # Merge in TODO items (deduplicated by content prefix)
    seen = set()
    for item in items:
        key = item["content"][:60]
        seen.add(key)
    for todo in found_todos[:5]:
        key = todo["content"][:60]
        if key not in seen:
            items.append(todo)
            seen.add(key)

    # Sort by score descending
    items.sort(key=lambda x: -x["score"])
    return items[:10]  # cap at 10 items


# ---------------------------------------------------------------------------
# HEARTBEAT.md writer
# ---------------------------------------------------------------------------

def now_shanghai() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")

def write_queue(heartbeat_path: Path, items: list[dict], mode: str) -> None:
    """Write queue items to HEARTBEAT.md."""
    rows = []
    for i, item in enumerate(items, 1):
        rows.append(
            f"| {i} | {item['type']} | {item['score']} | {item['content']} | {item['source']} | pending | {now_shanghai()} |"
        )

    queue_table = (
        "| # | Type | Score | Content | Source | Status | Created |\n"
        "|---|------|-------|---------|--------|--------|---------|\n"
        + "\n".join(rows)
    )

    content = heartbeat_path.read_text(encoding="utf-8") if heartbeat_path.exists() else ""

    # Replace Queue section
    queue_section_re = re.compile(r"(## Queue\n\n)>[^\n]*\n\n\|[^\n]+\n\|?[^\n]*\n([\s\S]*?)(?=\n---\n)")
    if queue_section_re.search(content):
        content = queue_section_re.sub(f"\\1{queue_table}\n\n---\n", content)
    else:
        content += f"\n\n## Queue\n\n{queue_table}\n"

    # Update mode to normal (since project is established)
    if mode == "existing":
        content = re.sub(r"(\| mode \|\s*)\w+(\s*\|)", f"\\1normal\\2", content)

    heartbeat_path.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Bootstrap a project for the Autonomous Improvement Loop. "
                    "Detects project state automatically and generates an initial queue."
    )
    parser.add_argument(
        "--project", required=True, type=Path,
        help="Path to the project directory"
    )
    parser.add_argument(
        "--skill-dir", required=True, type=Path,
        help="Path to the autonomous-improvement-loop skill directory"
    )
    parser.add_argument(
        "--mode",
        choices=["new", "existing", "detect"],
        default="detect",
        help="'new' = generate bootstrap queue, 'existing' = scan codebase, "
             "'detect' = auto-detect based on project readiness (default)"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Print what would be done without modifying any files"
    )
    parser.add_argument(
        "--report", action="store_true",
        help="Print project readiness report"
    )
    args = parser.parse_args()

    project = args.project.expanduser().resolve()
    if not project.exists():
        print(f"ERROR: Project path does not exist: {project}", file=sys.stderr)
        return 1

    heartbeat = args.skill_dir / "HEARTBEAT.md"

    # --- Readiness report ---
    if args.report:
        print(f"\n=== Project Readiness Report: {project.name} ===\n")
        checks = check_readiness(project)
        all_pass = True
        for check, result in checks.items():
            status = "PASS" if result else "FAIL"
            if not result:
                all_pass = False
            print(f"  [{status}] {check}")
        print()
        if all_pass:
            print("  Project is AI-ready. Mode: normal")
        else:
            print("  Project is NOT yet AI-ready. Mode: bootstrap")
            print("  Run without --report to generate a bootstrap queue.")
        print()
        return 0

    # --- Detect mode ---
    if args.mode == "detect":
        if is_new_project(project):
            mode = "new"
            print("Detected: NEW PROJECT (bootstrap queue will be generated)")
        else:
            mode = "existing"
            print("Detected: EXISTING PROJECT (codebase scan will run)")
    else:
        mode = args.mode

    # --- Generate queue items ---
    if mode == "new":
        lang = detect_language(project)
        if lang == ".py":
            items = list(PYTHON_NEW_PROJECT_BOOTSTRAP)
        else:
            items = list(GENERIC_NEW_PROJECT_BOOTSTRAP)
        print(f"\nGenerated {len(items)} bootstrap tasks for new project ({lang} detected):\n")
        for i, item in enumerate(items, 1):
            print(f"  {i}. [score={item['score']}] {item['content']}")
            if item.get("note"):
                print(f"      → {item['note']}")
    else:
        items = scan_existing_project(project)
        print(f"\nScanned {project.name} — found {len(items)} initial queue items:\n")
        for i, item in enumerate(items, 1):
            print(f"  {i}. [score={item['score']}] {item['content']}")

    # --- Write to HEARTBEAT.md ---
    if args.dry_run:
        print("\n[DRY RUN] No files written.")
        print(f"  Would write {len(items)} items to: {heartbeat}")
    else:
        if not heartbeat.exists():
            print(f"ERROR: HEARTBEAT.md not found at {heartbeat}", file=sys.stderr)
            return 1
        write_queue(heartbeat, items, mode)
        print(f"\nWrote {len(items)} items to {heartbeat}")
        print(f"Run Status mode set to: {'normal' if mode == 'existing' else 'bootstrap'}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
