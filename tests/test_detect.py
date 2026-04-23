from pathlib import Path

from scripts.detect import check_project_readiness, detect_telegram_chat_id, detect_version_file


def test_detect_version_file_accepts_uppercase_VERSION(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    version_file = project / "VERSION"
    version_file.write_text("1.2.3\n", encoding="utf-8")

    detected = detect_version_file(project)

    assert detected == version_file


def test_check_project_readiness_counts_uppercase_VERSION(tmp_path):
    project = tmp_path / "proj"
    project.mkdir()
    (project / "README.md").write_text("# demo\n", encoding="utf-8")
    (project / ".git").mkdir()
    (project / "docs").mkdir()
    (project / "tests").mkdir()
    (project / "VERSION").write_text("1.2.3\n", encoding="utf-8")

    checks = check_project_readiness(project)

    assert checks["version file"] is True


def test_detect_telegram_chat_id_reads_chat_id_key(tmp_path, monkeypatch):
    config_dir = tmp_path / ".openclaw" / "skills-config" / "autonomous-improvement-loop"
    config_dir.mkdir(parents=True)
    (config_dir / "config.md").write_text("chat_id: 5535183090\n", encoding="utf-8")
    monkeypatch.setenv("HOME", str(tmp_path))

    detected = detect_telegram_chat_id()

    assert detected == "5535183090"
