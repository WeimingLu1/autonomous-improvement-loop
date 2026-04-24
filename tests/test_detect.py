from pathlib import Path
from types import SimpleNamespace

from scripts.detect import check_project_readiness, detect_existing_crons, detect_telegram_chat_id, detect_version_file


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


def test_detect_existing_crons_returns_all_matching_ids(monkeypatch):
    payload = (
        '[{"id":"cron-1","label":"Autonomous Improvement Loop"},'
        '{"id":"cron-2","label":"Autonomous Improvement Loop"},'
        '{"id":"other","label":"Something Else"}]'
    )

    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=payload)

    monkeypatch.setattr("scripts.detect.subprocess.run", fake_run)

    assert detect_existing_crons() == ["cron-1", "cron-2"]
