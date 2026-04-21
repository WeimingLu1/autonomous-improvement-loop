from pathlib import Path

from scripts.plan_writer import write_plan_doc
from scripts.roadmap import init_roadmap, load_roadmap, append_done_log
from scripts.task_ids import next_task_id


def test_init_roadmap_creates_single_current_task_table(tmp_path: Path):
    roadmap = tmp_path / "ROADMAP.md"
    init_roadmap(roadmap)
    text = roadmap.read_text(encoding="utf-8")
    assert "## Current Task" in text
    assert "| task_id | type | source | title | status | created |" in text
    assert "## Done Log" in text


def test_load_roadmap_reads_empty_current_task(tmp_path: Path):
    roadmap = tmp_path / "ROADMAP.md"
    init_roadmap(roadmap)
    data = load_roadmap(roadmap)
    assert data.current_task is None
    assert data.next_default_type == "idea"
    assert data.improves_since_last_idea == 0


def test_next_task_id_starts_at_001(tmp_path: Path):
    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    assert next_task_id(plans_dir) == "TASK-001"


def test_next_task_id_increments_from_existing(tmp_path: Path):
    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    (plans_dir / "TASK-001.md").write_text("x", encoding="utf-8")
    (plans_dir / "TASK-004.md").write_text("x", encoding="utf-8")
    assert next_task_id(plans_dir) == "TASK-005"


def test_next_task_id_skips_gaps(tmp_path: Path):
    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    (plans_dir / "TASK-002.md").write_text("x", encoding="utf-8")
    (plans_dir / "TASK-005.md").write_text("x", encoding="utf-8")
    assert next_task_id(plans_dir) == "TASK-006"


def test_write_plan_doc_creates_file(tmp_path: Path):
    plans_dir = tmp_path / "plans"
    path = write_plan_doc(plans_dir, "TASK-001", "Add roadmap current-task echo", acceptance_criteria=["echo"])
    assert path.exists()
    assert path.name == "TASK-001.md"


def test_write_plan_doc_content_structure(tmp_path: Path):
    plans_dir = tmp_path / "plans"
    path = write_plan_doc(plans_dir, "TASK-001", "Add roadmap current-task echo", acceptance_criteria=["echo"])
    text = path.read_text(encoding="utf-8")
    assert "# TASK-001 · Add roadmap current-task echo" in text
    assert "## Acceptance Criteria" in text


def test_write_plan_doc_returns_path(tmp_path: Path):
    plans_dir = tmp_path / "plans"
    path = write_plan_doc(plans_dir, "TASK-001", "Add roadmap current-task echo", acceptance_criteria=["echo"])
    assert str(path).endswith("TASK-001.md")


def test_append_done_log_uses_new_table_shape(tmp_path: Path):
    roadmap = tmp_path / "ROADMAP.md"
    init_roadmap(roadmap)
    append_done_log(
        roadmap,
        task_id="TASK-001",
        task_type="idea",
        source="pm",
        title="Add roadmap export",
        result="pass",
        commit="abc1234",
        timestamp="2026-04-21T02:11:00Z",
    )
    text = roadmap.read_text(encoding="utf-8")
    assert "| 2026-04-21T02:11:00Z | TASK-001 | idea | pm | Add roadmap export | pass | abc1234 |" in text
