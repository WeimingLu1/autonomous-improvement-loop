from pathlib import Path

from scripts.cli import _collect_completed_titles_from_project_state


def test_collect_completed_titles_from_project_state_detects_benchmark_suite(tmp_path):
    project = tmp_path / "proj"
    (project / "benchmarks").mkdir(parents=True)
    (project / "benchmarks" / "run_benchmarks.py").write_text("print('ok')\n", encoding="utf-8")
    (project / ".gitignore").write_text("benchmarks/results.jsonl\n", encoding="utf-8")

    done_titles = _collect_completed_titles_from_project_state(project)

    assert "为项目增加性能基准测试，跟踪 a-plan / a-current 等命令的响应时间" in done_titles


def test_collect_completed_titles_from_project_state_detects_split_init_refactor(tmp_path):
    project = tmp_path / "proj"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    for name in ("cli.py", "cron.py", "detect.py", "state.py"):
        (scripts / name).write_text("# stub\n", encoding="utf-8")
    (scripts / "init.py").write_text("\n".join(["line"] * 120) + "\n", encoding="utf-8")

    done_titles = _collect_completed_titles_from_project_state(project)

    assert "审视 scripts/ 目录结构，将 2024 行的 init.py 拆分为 cli/、state/、cron/ 三个模块" in done_titles
