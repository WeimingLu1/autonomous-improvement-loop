from unittest.mock import patch

from scripts.state import ask


def test_ask_returns_default_on_eof():
    with patch("builtins.input", side_effect=EOFError):
        assert ask("Proceed?", "n") == "n"


def test_ask_returns_empty_string_on_eof_without_default():
    with patch("builtins.input", side_effect=EOFError):
        assert ask("Proceed?") == ""


from scripts.roadmap import load_roadmap
from scripts.state import seed_queue


def test_seed_queue_initializes_roadmap_with_current_task(tmp_path):
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    (tmp_path / "PROJECT.md").write_text("# Demo\n\nContext", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_smoke.py").write_text("def test_ok():\n    assert True\n", encoding="utf-8")

    seed_queue(tmp_path, mode="normal", language="zh")

    roadmap = load_roadmap(tmp_path / ".ail" / "ROADMAP.md")
    assert roadmap.current_task is not None
    assert roadmap.current_task.task_id == "TASK-001"
    assert (tmp_path / ".ail" / "plans" / "TASK-001.md").exists()
