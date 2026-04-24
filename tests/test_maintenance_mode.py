import pytest
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
