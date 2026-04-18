#!/usr/bin/env python3
"""Scan a project and append improvement candidates to HEARTBEAT.md.

This scanner is designed to keep the queue diverse, creative, and full of ideas
from user-experience and feature perspectives — not just code quality gaps.

It runs in two modes:
  --scan        Scan once and append ONE best candidate (default, used by cron)
  --refresh     Keep calling --scan until queue has at least N items (default: 5)

Usage (scan once):
    python queue_scanner.py --project . --heartbeat HEARTBEAT.md --language zh

Usage (refresh until 5 items):
    python queue_scanner.py --project . --heartbeat HEARTBEAT.md --language zh --refresh --min 5

Arguments:
    --project   Project root (required)
    --heartbeat Path to HEARTBEAT.md (required)
    --language  "zh" or "en" [default: zh]
    --refresh   Keep scanning until queue has at least --min items
    --min       Minimum queue size when using --refresh [default: 5]
    --repo      GitHub repo URL [default: https://github.com/OWNER/REPO]
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

# ── Bilingual idea buckets ────────────────────────────────────────────────────
# Each function returns a list of candidate strings for ONE scan call.
# Candidates are deduplicated against existing queue entries.

def rule_test_gaps(project: Path, lang: str = "zh") -> list[str]:
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
            if lang == "en":
                findings.append(f"Add unit tests for {py_file.name}")
            else:
                findings.append(f"为 {py_file.name} 补齐单元测试")
    return findings


def todo_findings(project: Path, lang: str = "zh") -> list[str]:
    findings: list[str] = []
    src_dir = project / "src"
    if not src_dir.is_dir():
        return findings
    for py_file in sorted(src_dir.rglob("*.py")):
        if "__pycache__" in str(py_file):
            continue
        for line_no, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), 1):
            if re.search(r"\b(TODO|FIXME|HACK|XXX)\b", line, re.IGNORECASE):
                if lang == "en":
                    findings.append(f"Address TODO at {_rel(py_file, project)}:{line_no}")
                else:
                    findings.append(f"处理 {_rel(py_file, project)}:{line_no} 的 TODO")
    return findings


def missing_docstrings(project: Path, lang: str = "zh") -> list[str]:
    findings: list[str] = []
    src_dir = project / "src"
    if not src_dir.is_dir():
        return findings
    for py_file in sorted(src_dir.rglob("*.py")):
        if "__pycache__" in str(py_file) or py_file.name.startswith("_"):
            continue
        head = py_file.read_text(encoding="utf-8")[:300]
        if '"""' not in head and "'''" not in head:
            if lang == "en":
                findings.append(f"Add module docstring to {_rel(py_file, project)}")
            else:
                findings.append(f"为 {_rel(py_file, project)} 补齐模块 docstring")
    return findings


def cli_json_gaps(project: Path, lang: str = "zh") -> list[str]:
    findings: list[str] = []
    cli_dir = project / "cli"
    if not cli_dir.is_dir():
        return findings
    for py_file in sorted(cli_dir.glob("*.py")):
        if py_file.stem in {"__init__", "__main__", "main"}:
            continue
        content = py_file.read_text(encoding="utf-8")
        if '"--json"' not in content and "'--json'" not in content:
            if lang == "en":
                findings.append(f"Add --json output to cli/{py_file.stem}")
            else:
                findings.append(f"为 cli/{py_file.stem} 增加 --json 输出")
    return findings


def service_test_gaps(project: Path, lang: str = "zh") -> list[str]:
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
            if lang == "en":
                findings.append(f"Add unit tests for services/{py_file.stem}")
            else:
                findings.append(f"为 services/{py_file.stem} 补齐单元测试")
    return findings


# ── Creative idea buckets (user-experience & feature focused) ────────────────
# These generate actual product improvement ideas, not just code hygiene.

def ux_improvements(project: Path, lang: str = "zh") -> list[str]:
    """Ideas from user experience perspective."""
    ideas: list[str] = []
    if lang == "en":
        ideas.extend([
            "Add colored emoji output for CLI commands to improve readability",
            "Add progress bar for long-running operations like data export",
            "Improve error messages: show suggested fix when a command fails",
            "Add shell completions (bash/zsh/fish) for the CLI",
            "Add interactive wizard mode for `health profile init`",
            "Add confirmation prompt before destructive commands (delete, reset)",
            "Add `--verbose` flag to show detailed execution info",
            "Support config file (~/.healthagent.yaml) to set defaults",
        ])
    else:
        ideas.extend([
            "为 CLI 输出增加彩色 emoji，提升可读性",
            "为耗时的操作（如导出）增加进度条",
            "改进错误提示：命令失败时给出修复建议",
            "为 CLI 增加 shell 自动补全（bash/zsh/fish）",
            "为 `health profile init` 增加交互式引导模式",
            "为危险命令（删除、重置）增加确认提示",
            "增加 `--verbose` 选项显示详细执行信息",
            "支持配置文件（~/.healthagent.yaml）设置默认参数",
        ])
    return ideas


def feature_enhancements(project: Path, lang: str = "zh") -> list[str]:
    """New feature ideas from product perspective."""
    ideas: list[str] = []
    if lang == "en":
        ideas.extend([
            "Add `health export timeline` command: export events as a readable daily timeline",
            "Add `health summary streak` command: show consecutive days of logging",
            "Add `health check --suggest` to not just report signals but suggest next actions",
            "Add `health log --undo` to undo the last logged event",
            "Add `health compare` command: compare this week vs last week",
            "Add tag/category support for events (e.g., 'workout:running', 'meal:low-carb')",
            "Add `health check --json` to output structured rule results",
            "Add `health profile export/import` to backup and restore profile data",
        ])
    else:
        ideas.extend([
            "新增 `health export timeline` 命令：导出为可读的每日时间线",
            "新增 `health summary streak` 命令：显示连续记录天数",
            "改进 `health check --suggest`：不仅报信号，还给出下一步行动建议",
            "新增 `health log --undo`：撤销上一条记录",
            "新增 `health compare` 命令：对比本周与上周的数据",
            "为事件增加标签/分类支持（如 'workout:running', 'meal:low-carb'）",
            "为 `health check` 增加 `--json` 输出结构化规则结果",
            "新增 `health profile export/import`：备份和恢复 profile 数据",
        ])
    return ideas


def intelligence_features(project: Path, lang: str = "zh") -> list[str]:
    """Smart / AI-adjacent feature ideas."""
    ideas: list[str] = []
    if lang == "en":
        ideas.extend([
            "Add `health insight` command: proactive health tip based on recent patterns",
            "Detect abnormal values automatically and warn user (e.g., unusually high BP)",
            "Add weekly health digest: summarize the week and highlight anomalies",
            "Add goal tracking: compare actual exercise/sleep vs user's set goals",
            "Predict next-week sleep/exercise trends based on historical patterns",
            "Add meal nutrition estimation hint when logging meals",
        ])
    else:
        ideas.extend([
            "新增 `health insight` 命令：基于近期规律主动推送健康提示",
            "自动检测异常数值并提醒用户（如血压异常高）",
            "新增每周健康摘要：总结本周数据并标注异常",
            "新增目标追踪：对比实际运动/睡眠与设定目标的差距",
            "基于历史数据预测下周睡眠/运动趋势",
            "记录饮食时自动估算营养素（热量、碳水、蛋白质）",
        ])
    return ideas


def data_capabilities(project: Path, lang: str = "zh") -> list[str]:
    """Data import/export and integration ideas."""
    ideas: list[str] = []
    if lang == "en":
        ideas.extend([
            "Add CSV import: bulk-import historical data from spreadsheets",
            "Add `health export json` for structured data export (already exists for some)",
            "Add Apple Health / Google Fit import integration",
            "Add `health backup` command: export entire database to a file",
            "Add `health restore` command: import backup file to restore data",
        ])
    else:
        ideas.extend([
            "新增 CSV 导入：批量从表格导入历史数据",
            "统一 `health export` 各子命令的 JSON 输出格式",
            "新增 Apple Health / Google Fit 数据导入集成",
            "新增 `health backup` 命令：导出完整数据库备份",
            "新增 `health restore` 命令：从备份文件恢复数据",
        ])
    return ideas


def engagement_features(project: Path, lang: str = "zh") -> list[str]:
    """Features that increase user engagement and consistency."""
    ideas: list[str] = []
    if lang == "en":
        ideas.extend([
            "Add achievement badges: 'First Log', '7-day streak', 'Marathon month'",
            "Add motivational messages when user maintains a good streak",
            "Add daily check-in reminder via system notification",
            "Add `health score` command: give an overall health score 0-100",
            "Add leaderboard: track personal bests across time periods",
        ])
    else:
        ideas.extend([
            "新增成就徽章：'首次记录'、'连续7天'、'运动达人月'",
            "当用户保持连续记录时发送激励消息",
            "新增每日签到提醒（系统通知）",
            "新增 `health score` 命令：给出综合健康评分 0-100",
            "新增个人记录排行榜：追踪不同时段的最佳成绩",
        ])
    return ideas


def _rel(py_file: Path, root: Path) -> str:
    try:
        return str(py_file.relative_to(root))
    except ValueError:
        return str(py_file)


# ── All buckets combined (scan order) ─────────────────────────────────────────

def all_buckets(project: Path, lang: str = "zh") -> list[tuple[str, str]]:
    """Return list of (bucket_name, finding) tuples in priority order."""
    buckets = [
        ("test", rule_test_gaps(project, lang)),
        ("service", service_test_gaps(project, lang)),
        ("todo", todo_findings(project, lang)),
        ("doc", missing_docstrings(project, lang)),
        ("cli", cli_json_gaps(project, lang)),
        ("ux", ux_improvements(project, lang)),
        ("feature", feature_enhancements(project, lang)),
        ("intelligence", intelligence_features(project, lang)),
        ("data", data_capabilities(project, lang)),
        ("engage", engagement_features(project, lang)),
    ]
    result: list[tuple[str, str]] = []
    for _, findings in buckets:
        for f in findings:
            result.append((bucket_name, f))
    return result


# ── Core logic ────────────────────────────────────────────────────────────────

def existing_queue_normalized(heartbeat: Path) -> set[str]:
    content = heartbeat.read_text(encoding="utf-8")
    rows = re.findall(r'\|\s*\d+\s*\|[^|]*\|\s*([^|]+?)\s*\|', content)
    return {normalize(f) for f in rows}


def normalize(text: str) -> str:
    return re.sub(r'\s+', ' ', text.strip())


def choose_best_candidate(project: Path, heartbeat: Path, lang: str = "zh") -> str | None:
    """Pick the highest-priority new finding from all buckets."""
    existing = existing_queue_normalized(heartbeat)
    for bucket_name, finding in all_buckets(project, lang):
        if normalize(finding) not in existing:
            return finding
    return None


def append_to_queue(heartbeat: Path, repo: str, finding: str) -> bool:
    """Append one entry to the Queue section of HEARTBEAT.md."""
    content = heartbeat.read_text(encoding="utf-8")
    section_match = re.search(r'(## Queue\n\n)([\s\S]*?)(\n---\n)', content)
    if not section_match:
        print("ERROR: Queue section not found in HEARTBEAT.md", file=sys.stderr)
        return False

    # Score it
    score = _score_finding(finding)

    section_body = section_match.group(2)
    numbers = [int(m) for m in re.findall(r'^\|\s*(\d+)\s*\|', section_body, re.MULTILINE)]
    next_num = max(numbers) + 1 if numbers else 1
    created = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    new_line = f"{next_num}. [[Improve]] score={score} | {finding} | scanner | pending | {created}"
    new_section = section_match.group(1) + section_body.rstrip() + "\n" + new_line + "\n" + section_match.group(3)
    updated = content[:section_match.start()] + new_section + content[section_match.end():]
    heartbeat.write_text(updated, encoding="utf-8")
    print(f"queue_scanner: +1 -> {new_line}")
    return True


def _score_finding(finding: str) -> int:
    """Score a finding based on its category/keywords."""
    finding_lower = finding.lower()
    if any(k in finding_lower for k in ['test', '单元测试', '单元测验']):
        return 50
    if any(k in finding_lower for k in ['docstring', 'doc', '文档']):
        return 45
    if any(k in finding_lower for k in ['insight', '智能', '预测', 'detect', '检测', 'score', '评分']):
        return 72
    if any(k in finding_lower for k in ['export', 'import', 'backup', 'restore', '导入', '导出', '备份', '恢复']):
        return 65
    if any(k in finding_lower for k in ['achievement', 'badge', 'streak', '成就', '徽章', '连续', '排行榜']):
        return 68
    if any(k in finding_lower for k in ['suggest', 'compare', 'undo', 'wizard', 'completion', '建议', '对比', '撤销', '补全']):
        return 70
    if any(k in finding_lower for k in ['health check', 'check --json', '规则']):
        return 62
    if any(k in finding_lower for k in ['error', 'verbose', 'config', 'confirm', '错误', '详细', '配置', '确认']):
        return 55
    return 60


def queue_count(heartbeat: Path) -> int:
    """Count pending entries in queue."""
    content = heartbeat.read_text(encoding="utf-8")
    pending = re.findall(r'\|\s*(\d+)\s*\|[^|]*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|', content)
    return sum(1 for row in pending if 'pending' in row[-1].lower())


def refresh_queue(project: Path, heartbeat: Path, repo: str, lang: str, min_items: int) -> int:
    """Keep scanning and appending until queue has at least min_items pending."""
    added = 0
    while queue_count(heartbeat) < min_items:
        candidate = choose_best_candidate(project, heartbeat, lang)
        if not candidate:
            print("queue_scanner: no more candidates found, queue has "
                  f"{queue_count(heartbeat)} items")
            break
        if append_to_queue(heartbeat, repo, candidate):
            added += 1
    if added:
        print(f"queue_scanner: refreshed queue, added {added} items "
              f"(total pending: {queue_count(heartbeat)})")
    return added


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scan project and append improvement candidates to HEARTBEAT.md"
    )
    parser.add_argument("--project", required=True, type=Path, help="Project root")
    parser.add_argument("--heartbeat", required=True, type=Path, help="Path to HEARTBEAT.md")
    parser.add_argument("--language", default="zh", choices=["en", "zh"],
                        help='Output language [default: zh]')
    parser.add_argument("--refresh", action="store_true",
                        help="Keep scanning until queue has at least --min items")
    parser.add_argument("--min", type=int, default=5,
                        help="Minimum queue size when using --refresh [default: 5]")
    parser.add_argument("--repo", default=HEARTBEAT_TEMPLATE, help="GitHub repo URL")
    args = parser.parse_args()

    if args.refresh:
        added = refresh_queue(Path(args.project), Path(args.heartbeat),
                              args.repo, args.language, args.min)
        return 0 if added >= 0 else 1

    candidate = choose_best_candidate(Path(args.project), Path(args.heartbeat), args.language)
    if not candidate:
        print("queue_scanner: no new improvement candidate found")
        return 0
    return 0 if append_to_queue(Path(args.heartbeat), args.repo, candidate) else 1


if __name__ == "__main__":
    raise SystemExit(main())
