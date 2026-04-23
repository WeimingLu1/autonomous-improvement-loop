"""
Multi-project management for Autonomous Improvement Loop.

Supports managing multiple projects from a single workspace, with:
- multi_project.cfg configuration file (simple key=value, no external deps)
- a-status --all: show status of all registered projects
- a-switch: switch active project

Config file format (~/.openclaw/skills-config/autonomous-improvement-loop/multi_project.cfg):
    # comment
    /Users/weiminglu/Projects/project1 = My Project
    /Users/weiminglu/Projects/project2 = Quant Strategies
    active = /Users/weiminglu/Projects/project1
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path


CONFIG_FILE_NAME = "multi_project.cfg"
SKILL_CONFIG_HOME = Path.home() / ".openclaw" / "skills-config" / "autonomous-improvement-loop"
ACTIVE_PROJECT_FILE = SKILL_CONFIG_HOME / ".active_project"


@dataclass
class ProjectEntry:
    path: Path
    alias: str
    name: str  # display name (defaults to alias)


def get_multi_project_config() -> Path | None:
    """Return the multi_project.cfg path if it exists."""
    config_path = SKILL_CONFIG_HOME / CONFIG_FILE_NAME
    return config_path if config_path.exists() else None


def load_multi_project_config() -> dict[str, str]:
    """Load and parse multi_project.cfg (simple key=value format).
    
    Lines can be:
      # comment
      /path/to/project = Display Name
      active = /path/to/project
    """
    config_path = get_multi_project_config()
    if not config_path:
        return {}
    result: dict[str, str] = {}
    try:
        with open(config_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, val = line.split("=", 1)
                    result[key.strip()] = val.strip()
    except Exception:
        pass
    return result


def get_active_project() -> Path | None:
    """Return the currently active project path, or None."""
    if not ACTIVE_PROJECT_FILE.exists():
        return None
    try:
        content = ACTIVE_PROJECT_FILE.read_text(encoding="utf-8").strip()
        p = Path(content)
        return p if p.exists() else None
    except Exception:
        return None


def set_active_project(project_path: Path) -> None:
    """Set the active project path."""
    SKILL_CONFIG_HOME.mkdir(parents=True, exist_ok=True)
    ACTIVE_PROJECT_FILE.write_text(str(project_path.resolve()), encoding="utf-8")


def list_registered_projects() -> list[ProjectEntry]:
    """Return all projects registered in multi_project.cfg."""
    config = load_multi_project_config()
    result = []
    for key, val in config.items():
        if key == "active":
            continue
        path = Path(key).expanduser()
        name = val if val else path.name
        result.append(ProjectEntry(path=path, alias=key, name=name))
    return result


def resolve_project_from_config(explicit_path: Path | None = None) -> Path | None:
    """Resolve the project path to use.
    Priority:
    1. explicit_path argument
    2. get_active_project() (a-switch set)
    3. None (single-project mode, caller will auto-detect)
    """
    if explicit_path:
        return explicit_path
    active = get_active_project()
    if active:
        return active
    return None


# ── CLI helpers ──────────────────────────────────────────────────────────────

def cmd_switch(alias_or_path: str) -> bool:
    """Switch the active project by alias or path. Returns True on success."""
    projects = list_registered_projects()
    matched = None

    # Try exact alias match
    for p in projects:
        if p.alias == alias_or_path:
            matched = p
            break

    # Try path match
    if not matched:
        candidate = Path(alias_or_path).expanduser().resolve()
        for p in projects:
            if p.path.resolve() == candidate:
                matched = p
                break
        # If not found in config but path exists, accept it as-is
        if not matched and candidate.exists():
            matched = ProjectEntry(path=candidate, alias=str(candidate), name=candidate.name)

    if not matched:
        return False

    set_active_project(matched.path)
    return True


_COLOR_RED = "\033[91m"
_COLOR_YELLOW = "\033[93m"
_COLOR_GREEN = "\033[92m"
_COLOR_RESET = "\033[0m"


def _c(text: str, color: str) -> str:
    return f"{globals().get(f'_COLOR_{color.upper()}', '')}{text}{_COLOR_RESET}"


def cmd_status_all() -> None:
    """Print status of all registered projects."""
    config = load_multi_project_config()
    if not config:
        print("  No multi_project.cfg found.")
        print(f"  Config location: {SKILL_CONFIG_HOME / CONFIG_FILE_NAME}")
        print("  Format: /path/to/project = Display Name  (one per line, # for comments)")
        return

    from scripts.roadmap import load_roadmap
    from scripts.state import ail_roadmap

    projects = list_registered_projects()
    active = get_active_project()

    print(f"\n{'#' * 60}")
    print(f"  Multi-Project Status ({len(projects)} registered)")
    print(f"{'#' * 60}")

    for p in projects:
        marker = "  [active]" if (active and p.path.resolve() == active.resolve()) else ""
        print(f"\n  {p.name}{marker}")
        print(f"  Path: {p.path}")

        if not p.path.exists():
            print(f"  {_c('⚠ project path does not exist', 'yellow')}")
            continue

        roadmap_path = ail_roadmap(p.path)
        if not roadmap_path.exists():
            print(f"  {_c('⚠ no ROADMAP.md found', 'yellow')}")
            continue

        try:
            roadmap = load_roadmap(roadmap_path)
            ct = roadmap.current_task
            if ct:
                print(f"  Current: [{ct.task_id}] {ct.title}")
                print(f"  Status: {ct.status} | Type: {ct.task_type}")
            else:
                print(f"  Current: {_c('(none — run a-plan)', 'yellow')}")
        except Exception as e:
            print(f"  {_c(f'Error loading roadmap: {e}', 'red')}")
