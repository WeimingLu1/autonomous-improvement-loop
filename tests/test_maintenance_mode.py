import pytest
import subprocess
import sys
from pathlib import Path
from scripts.roadmap import RoadmapState, CurrentTask

def test_roadmap_has_maintenance_mode_field():
    rs = RoadmapState(
        current_task=None,
        next_default_type="improve",
        improves_since_last_idea=0,
        post_feature_maintenance_remaining=0,
        maintenance_anchor_title="",
        current_plan_path="",
        reserved_user_task_id="",
    )
    assert hasattr(rs, "maintenance_mode")
    assert rs.maintenance_mode == False

def test_maintenance_candidates_exist():
    from scripts.task_planner import _MAINTENANCE_CANDIDATES
    assert len(_MAINTENANCE_CANDIDATES) >= 10
    tags = {c.get("maintenance_tag", "") for c in _MAINTENANCE_CANDIDATES}
    assert "testing" in tags
    assert "docs" in tags
    assert "deps" in tags


# ── CLI a-maintenance command tests ─────────────────────────────────────────
#
# These tests exercise the real `init.py` CLI as a subprocess.
# Since _get_roadmap_and_project() reads the global config's project_path
# (which always points to the AIL skill's own .ail/), we run the command
# from the AIL project directory itself and back up / restore ROADMAP.md.

_PROJECT = Path(__file__).resolve().parents[1]
_INIT_PY = str(_PROJECT / "scripts" / "init.py")
_ROADMAP_PATH = _PROJECT / ".ail" / "ROADMAP.md"


def _maintenance_run(action: str, initial_content: str) -> tuple[subprocess.CompletedProcess, str]:
    """Write initial_content to the real ROADMAP, run 'a-maintenance <action>', return (result, updated_content)."""
    # Backup
    had_roadmap = _ROADMAP_PATH.exists()
    saved = _ROADMAP_PATH.read_bytes() if had_roadmap else None

    # Write initial state
    _ROADMAP_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ROADMAP_PATH.write_text(initial_content, encoding="utf-8")

    try:
        result = subprocess.run(
            [sys.executable, _INIT_PY, "a-maintenance", action],
            cwd=str(_PROJECT),
            capture_output=True,
            text=True,
        )
        updated = _ROADMAP_PATH.read_text(encoding="utf-8")
        return result, updated
    finally:
        # Restore
        if saved is not None:
            _ROADMAP_PATH.write_bytes(saved)
        elif _ROADMAP_PATH.exists():
            _ROADMAP_PATH.unlink()


_ROADMAP_FALSE = (
    "# Roadmap\n\n"
    "## Rhythm State\n\n"
    "| field | value |\n"
    "|------|-------|\n"
    "| next_default_type | improve |\n"
    "| improves_since_last_idea | 0 |\n"
    "| maintenance_mode | false |\n"
)

_ROADMAP_TRUE = (
    "# Roadmap\n\n"
    "## Rhythm State\n\n"
    "| field | value |\n"
    "|------|-------|\n"
    "| next_default_type | improve |\n"
    "| improves_since_last_idea | 0 |\n"
    "| maintenance_mode | true |\n"
)

_ROADMAP_TRUE_MINIMAL = (
    "# Roadmap\n\n"
    "## Rhythm State\n\n"
    "| field | value |\n"
    "|------|-------|\n"
    "| maintenance_mode | true |\n"
)


def test_maintenance_command_on():
    result, content = _maintenance_run("on", _ROADMAP_FALSE)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "maintenance_mode | true" in content


def test_maintenance_command_off():
    result, content = _maintenance_run("off", _ROADMAP_TRUE)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "maintenance_mode | false" in content


def test_maintenance_command_status():
    result, _ = _maintenance_run("status", _ROADMAP_TRUE_MINIMAL)
    assert result.returncode == 0, f"stdout={result.stdout}\nstderr={result.stderr}"
    assert "enabled" in result.stdout.lower()


def test_maintenance_command_unknown_action():
    result, _ = _maintenance_run("xyz", _ROADMAP_FALSE)
    assert result.returncode != 0
