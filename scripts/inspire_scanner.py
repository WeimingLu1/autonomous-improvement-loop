#!/usr/bin/env python3
"""
inspire_scanner.py — generate alternating [[Idea]]/[[Improve]] tasks from project analysis.

Runs AFTER update_heartbeat normal queue refresh. Each call decides the next task
type (idea or improve) via _decide_next_type(), generates a candidate, picks the
best one, and injects it into HEARTBEAT queue — replacing any existing row of
the same type.

Unlike the [[Improve]] scanner (which finds explicit tag markers in code),
inspire_scanner uses project-type + inspire questions to REASON about gaps
that no one has tagged yet — real new features, not just "add more tests".

Usage:
    from inspire_scanner import run_inspire_scan
    run_inspire_scan(project, heartbeat, language)
"""
from __future__ import annotations

import re
import argparse
from pathlib import Path
from datetime import datetime, timezone

from project_insights import _parse_all_queue_rows, _render_queue_block, _replace_all_queue_sections, detect_project_type as _detect_project_type

# ── Alternation state helpers ───────────────────────────────────────────────

def _get_last_done_type(heartbeat: Path) -> str | None:
    """Read the most recent Done Log data row and return its task type.

    Parses the Done Log section, finds the LAST data row
    (format: | time | commit | task | result |), and checks the task field.
    Returns "idea", "improve", or None if no entries.
    """
    if not heartbeat.exists():
        return None
    text = heartbeat.read_text(encoding="utf-8", errors="ignore")

    # Find the Done Log section
    m = re.search(r"##\s*Done\s*Log\s*\n[\s\S]*?(?=##\s|\Z)", text)
    if not m:
        return None
    section = m.group(0)

    # Find all data rows (skip header and separator lines)
    rows = re.findall(r"\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|", section)
    if not rows:
        return None

    # Take the LAST data row
    _time, _commit, task, _result = rows[-1]
    if "[[Idea]]" in task:
        return "idea"
    if "[[Improve]]" in task:
        return "improve"
    return None


def _get_improves_since_idea(heartbeat: Path) -> int:
    """Read improves_since_last_idea counter from Run Status table.

    Pattern: | improves_since_last_idea | N |
    Returns int N, default 0 if not found.
    """
    if not heartbeat.exists():
        return 0
    text = heartbeat.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"\|\s*improves_since_last_idea\s*\|\s*(\d+)\s*\|", text)
    if m:
        return int(m.group(1))
    return 0


def _set_last_generated_content(heartbeat: Path, content: str) -> None:
    '''Store last generated item normalized content in Run Status.
    
    Prevents immediate re-generation when a-refresh is called twice without
    the agent executing the task.
    '''
    text = heartbeat.read_text(encoding='utf-8', errors='ignore')
    normalized = _normalize_text(content)
    content_row = f'| last_generated_content | {normalized} |'
    if re.search(r'\|\s*last_generated_content\s*\|', text):
        text = re.sub(
            r'(\|\s*last_generated_content\s*\|\s*).+?(\s*\|)',
            lambda m: f'{m.group(1)}{normalized}{m.group(2)}',
            text,
            count=1,
        )
    elif '## Run Status' in text:
        rs_m = re.search(r'(\| Field \| Value \|\n\|[- ]+\|[- ]+\|\n((?:\|.*\|\n)*))', text)
        if rs_m:
            existing = rs_m.group(2).rstrip('\n')
            new_rows = existing + f'\n{content_row}\n'
            text = text[:rs_m.start(2)] + new_rows + text[rs_m.end(2):]
    heartbeat.write_text(text, encoding='utf-8')


def _get_last_generated_content(heartbeat: Path) -> str | None:
    '''Read last_generated_content (normalized) from Run Status, or None.'''
    if not heartbeat.exists():
        return None
    text = heartbeat.read_text(encoding='utf-8', errors='ignore')
    m = re.search(r'\|\s*last_generated_content\s*\|\s*(.+?)\s*\|', text)
    return m.group(1).strip() if m else None


def _set_improves_since_idea(heartbeat: Path, count: int) -> None:
    """Update or insert improves_since_last_idea row in Run Status.

    Also cleans up legacy fields:
    - Removes any HTML comment <!-- inspire_scan_cycle: N -->
    - Removes any plain row | inspire_scan_cycle | N |
    """
    if not heartbeat.exists():
        return
    text = heartbeat.read_text(encoding="utf-8", errors="ignore")

    # 1. Remove legacy HTML comment <!-- inspire_scan_cycle: N -->
    text = re.sub(r"<!--\s*inspire_scan_cycle:\s*\d+\s*-->\s*", "", text)

    # 2. Remove legacy plain row | inspire_scan_cycle | N |
    text = re.sub(r"\n?\|\s*inspire_scan_cycle\s*\|\s*\d+\s*\|\s*", "\n", text)

    # 3. Update or insert | improves_since_last_idea | N |
    counter_row = f"| improves_since_last_idea | {count} |"
    if re.search(r"\|\s*improves_since_last_idea\s*\|\s*\d+\s*\|", text):
        text = re.sub(
            r"(\|\s*improves_since_last_idea\s*\|\s*)\d+(\s*\|)",
            rf"\g<1>{count}\g<2>",
            text,
            count=1,
        )
    elif "## Run Status" in text:
        # Insert into Run Status table after the last | Field | Value | row
        # Find the Run Status table body and append after its last row
        rs_m = re.search(r"(\| Field \| Value \|\n\|[- ]+\|[- ]+\|\n)((?:\|.*\|\n)*)", text)
        if rs_m:
            existing_rows = rs_m.group(2)
            # Remove trailing empty lines
            existing_rows = existing_rows.rstrip("\n")
            # Find the last row to insert after (insert before any Notes or other sections)
            new_rows = existing_rows + f"\n{counter_row}\n"
            text = text[: rs_m.start(2)] + new_rows + text[rs_m.end(2) :]

    heartbeat.write_text(text, encoding="utf-8")


def _decide_next_type(heartbeat: Path) -> str:
    """Core alternation logic — pure read-only, no side effects.

    Rules:
    - No entries → "idea"
    - Last was "idea" → "improve"
    - Last was "improve":
        - if counter >= 2 → "idea"  (threshold reached, flip)
        - else             → "improve"  (continue improve streak)

    Counter is NOT updated here. Caller updates Run Status after generation.
    """
    last_type = _get_last_done_type(heartbeat)
    if last_type is None:
        return "idea"
    if last_type == "idea":
        return "improve"
    # last_type == "improve"
    counter = _get_improves_since_idea(heartbeat)
    if counter >= 2:
        return "idea"
    return "improve"


def _get_recent_git_activity(project: Path, n: int = 20) -> list[tuple[str, int]]:
    """Run `git log --oneline -N --stat -- *.py` in the project directory.


    Parse stat output to count total lines changed per Python module.
    Returns list of (module_path, lines_changed) sorted descending by activity.
    Module path format: services/event_service.py, cli/check.py, etc.
    Returns empty list if not a git repo or git fails.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["git", "log", f"--oneline", f"-n{n}", "--stat", "--", "*.py"],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []

    # Parse stat output. Each file entry looks like:
    #   services/event_service.py    | 42 +++---
    # or
    #   cli/check.py                |  5 +-
    lines_changed: dict[str, int] = {}
    for line in result.stdout.splitlines():
        line = line.rstrip()
        if not line or line.startswith("commit ") or "/" not in line:
            continue
        # Match: filename | N +-
        m = re.match(r"^(\S[^*]*?\.py)\s*\|\s*(\d+)", line)
        if m:
            module = m.group(1).strip()
            changed = int(m.group(2))
            lines_changed[module] = lines_changed.get(module, 0) + changed

    return sorted(lines_changed.items(), key=lambda x: -x[1])


def _module_matches(module: str, fragment: str) -> bool:
    return module.startswith(fragment) or f"/{fragment}" in module


def _software_improve_generator(project: Path, language: str, seen: set[str]) -> list[tuple[str, str, int]]:
    """Generate multiple Improve candidates from recent Git activity."""
    activity = _get_recent_git_activity(project, n=30)
    results: list[tuple[str, str, int]] = []

    for module, _changed in activity:
        if language == "zh":
            if _module_matches(module, "services/"):
                content = (
                    f"基于最近 Git 提交分析，{module} 是高频改动模块。"
                    "建议：补充该模块所有公开函数的边界测试（None/空列表/异常输入），"
                    "并验证公开 API 的合约是否完整。"
                )
            elif _module_matches(module, "cli/"):
                content = (
                    f"{module} 最近改动较多，建议审查并补充错误处理和边界测试，"
                    "确保 --help 和 --json 两种输出模式均有测试覆盖。"
                )
            elif _module_matches(module, "rules/"):
                content = (
                    f"{module} 规则引擎最近有改动，建议补充完整边界情况测试"
                    "（窗口边界、None 字段、极端值）。"
                )
            elif _module_matches(module, "parsers/"):
                content = (
                    f"{module} 最近有更新，建议补充解析器的边界测试"
                    "（空输入、畸形输入、特殊字符、超长输入）。"
                )
            else:
                content = (
                    f"最近高频改动的 {module} 建议进行全面审查，"
                    "补充单元测试、错误路径测试和 docstring。"
                )
        else:
            if _module_matches(module, "services/"):
                content = (
                    f"Based on recent Git commits, {module} is a high-churn module. "
                    "Add boundary tests (None/empty-list/exception inputs) for public functions, "
                    "and verify public API contracts."
                )
            elif _module_matches(module, "cli/"):
                content = (
                    f"{module} has seen many recent changes. Add error-handling and boundary tests, "
                    "covering both --help and --json output modes."
                )
            elif _module_matches(module, "rules/"):
                content = (
                    f"{module} has recent rule-engine changes. Add boundary tests for window edges, "
                    "None fields, and extreme values."
                )
            elif _module_matches(module, "parsers/"):
                content = (
                    f"{module} has recent parser changes. Add tests for empty, malformed, special-char, "
                    "and oversized input."
                )
            else:
                content = (
                    f"Frequently changed module {module} should be reviewed: add unit tests, "
                    "error-path tests, and docstrings."
                )

        norm = _normalize_text(content)
        if norm in seen:
            continue
        results.append((content, content, 45))
        seen.add(norm)
        if len(results) >= 8:
            return results

    fallback_texts = [
        (
            "为关键用户流程增加集成测试，确保真实 CLI 调用链在重构后仍然稳定"
            if language == "zh"
            else "Add integration tests for critical user flows so real CLI call chains stay stable after refactors"
        ),
        (
            "确保所有错误路径都有对应测试，尤其是参数校验、空输入和数据库异常"
            if language == "zh"
            else "Ensure every error path has tests, especially validation, empty-input, and database-exception flows"
        ),
        (
            "为每个未充分覆盖的模块补齐单元测试，并清理重复或缺少说明的断言"
            if language == "zh"
            else "Backfill unit tests for under-covered modules and clean up repetitive or unclear assertions"
        ),
        (
            "为未写文档的模块补充 docstring，明确输入、输出和失败语义"
            if language == "zh"
            else "Add docstrings for undocumented modules, clarifying inputs, outputs, and failure semantics"
        ),
    ]
    for content in fallback_texts:
        norm = _normalize_text(content)
        if norm in seen:
            continue
        results.append((content, content, 45))
        seen.add(norm)

    return results


def _writing_improve_generator(project: Path, language: str, seen: set[str]) -> list[tuple[str, str, int]]:
    """Return multiple chapter-review Improve candidates."""
    chapters_dir = project / "chapters"
    if not chapters_dir.is_dir():
        return []

    try:
        files = sorted(
            [
                (f, f.stat().st_mtime)
                for f in chapters_dir.iterdir()
                if f.is_file() and f.suffix in (".md", ".txt", ".rst")
            ],
            key=lambda item: item[1],
        )
    except Exception:
        return []

    results: list[tuple[str, str, int]] = []
    for file_path, _ in files[:6]:
        name = file_path.name
        content = (
            f"章节 {name} 是较久未更新的内容，建议审查完整性、论证逻辑和与最新章节的衔接。"
            if language == "zh"
            else f"Chapter {name} is relatively stale. Review completeness, argument flow, and alignment with recent chapters."
        )
        norm = _normalize_text(content)
        if norm in seen:
            continue
        results.append((content, content, 45))
        seen.add(norm)
    return results


def _video_improve_generator(project: Path, language: str, seen: set[str]) -> list[tuple[str, str, int]]:
    """Return multiple scene-review Improve candidates."""
    scenes_dir = project / "scenes"
    if not scenes_dir.is_dir():
        return []

    try:
        files = sorted(
            [(f, f.stat().st_mtime) for f in scenes_dir.iterdir() if f.is_file()],
            key=lambda item: item[1],
        )
    except Exception:
        return []

    results: list[tuple[str, str, int]] = []
    for file_path, _ in files[:6]:
        name = file_path.name
        content = (
            f"场景 {name} 是较久未更新的内容，建议审查脚本完整度、镜头节奏和画面质量。"
            if language == "zh"
            else f"Scene {name} is relatively stale. Review script completeness, pacing, and visual quality."
        )
        norm = _normalize_text(content)
        if norm in seen:
            continue
        results.append((content, content, 45))
        seen.add(norm)
    return results


def _research_improve_generator(project: Path, language: str, seen: set[str]) -> list[tuple[str, str, int]]:
    """Return multiple research-project Improve candidates."""
    contents = [
        (
            "全面审查研究中的假设、证据链和引用完整性，补齐最薄弱的一环。"
            if language == "zh"
            else "Audit assumptions, evidence chains, and citation completeness, then strengthen the weakest link first."
        ),
        (
            "检查结论是否都能追溯到明确证据，避免存在跳步推理。"
            if language == "zh"
            else "Check whether every conclusion traces back to explicit evidence, avoiding reasoning gaps."
        ),
        (
            "把最关键的一章做一次结构重构，提升论证节奏和可读性。"
            if language == "zh"
            else "Restructure the most critical chapter to improve argument pacing and readability."
        ),
    ]
    results: list[tuple[str, str, int]] = []
    for content in contents:
        norm = _normalize_text(content)
        if norm in seen:
            continue
        results.append((content, content, 45))
        seen.add(norm)
    return results


def _generic_improve_generator(project: Path, language: str, seen: set[str]) -> list[tuple[str, str, int]]:
    """Return multiple generic Improve candidates."""
    contents = [
        (
            "审视项目，优先修复最影响用户效率的一个具体问题。"
            if language == "zh"
            else "Inspect the project and fix the single issue that hurts user efficiency the most."
        ),
        (
            "找出最容易引发返工的流程，补齐检查点或自动化保护。"
            if language == "zh"
            else "Find the workflow most likely to cause rework and add checkpoints or automation around it."
        ),
        (
            "检查最常被修改的部分，补齐缺失文档、测试或错误处理。"
            if language == "zh"
            else "Review the most frequently changed area and backfill missing docs, tests, or error handling."
        ),
        (
            "找出一个低成本但高感知价值的小改进，并把它落地。"
            if language == "zh"
            else "Identify one low-cost but high-perceived-value improvement and ship it."
        ),
    ]
    results: list[tuple[str, str, int]] = []
    for content in contents:
        norm = _normalize_text(content)
        if norm in seen:
            continue
        results.append((content, content, 45))
        seen.add(norm)
    return results


IMPROVE_GENERATORS: dict[str, callable] = {
    "software":  _software_improve_generator,
    "writing":   _writing_improve_generator,
    "video":     _video_improve_generator,
    "research":  _research_improve_generator,
    "generic":   _generic_improve_generator,
}


HEARTBEAT = Path(__file__).parent.parent / "HEARTBEAT.md"
SKILL_DIR = Path(__file__).parent.parent
PROJECT_MD = SKILL_DIR / "PROJECT.md"

# ── Inspiration questions per project kind ──────────────────────────────────

SOFTWARE_ZH = [
    "哪些开发者体验痛点还没被解决？",
    "CLI 工具有哪些交互范式可以创新？",
    "竞品的哪些亮点功能我们可以借鉴但还未实现？",
]
SOFTWARE_EN = [
    "What developer-experience pain points remain unsolved?",
    "What CLI interaction paradigms could be innovated?",
    "What competitor features could we adopt that we haven't yet?",
]
WRITING_ZH = [
    "作品结构有哪些可以优化的地方？",
    "有哪些读者反馈还没被转化为具体改进？",
]
VIDEO_ZH = [
    "视频内容有哪些薄弱环节观众可能不喜欢？",
    "制作流程中有哪些可以自动化或提速的步骤？",
]
RESEARCH_ZH = [
    "研究假设有没有被新文献推翻的风险？",
    "论文中有哪些论证链条还不够严谨？",
]
GENERIC_ZH = [
    "这个项目最影响使用体验的问题是什么？",
    "有没有明显缺失但应该有的功能？",
]

# ── Concrete idea generators (software, zh) ─────────────────────────────────

SOFTWARE_IDEA_GENERATORS_ZH = [
    {
        "trigger": "cli",
        "question": "CLI 工具有哪些交互范式可以创新？",
        "candidates": [
            ("添加交互式 `health interactive` 命令，通过问答引导记录健康事件，降低输入门槛",
             "src/cli/interactive.py"),
            ("为 `health log` 添加 `--dry-run` 选项，先预览解析结果再决定是否写入",
             "src/cli/log.py"),
            ("支持 `health check --format table|json|markdown` 多格式输出",
             "src/cli/check.py"),
        ],
    },
    {
        "trigger": "advisor",
        "question": "竞品的哪些亮点功能我们可以借鉴但还未实现？",
        "candidates": [
            ("为 `health advisor` 添加方案执行追踪面板，显示每条建议的执行状态",
             "src/services/health_advisor_service.py"),
            ("支持 `health advisor plan --goal <描述>` 根据用户目标生成定制化方案",
             "src/services/health_advisor_service.py"),
        ],
    },
    {
        "trigger": "summary",
        "question": "哪些开发者体验痛点还没被解决？",
        "candidates": [
            ("添加 `health summary digest --days 7`，自动汇总本周关键变化和异常信号",
             "src/services/summary_service.py"),
            ("`health status` 增加最近7天关键指标趋势图，用 ASCII art 显示",
             "src/cli/status.py"),
        ],
    },
    {
        "trigger": "log",
        "question": "CLI 工具有哪些交互范式可以创新？",
        "candidates": [
            ("为 `health log` 支持批量导入 CSV/JSON 文件批量录入历史数据",
             "src/cli/log.py"),
            ("添加 `health log edit <event-id>` 命令修正已记录的错误事件",
             "src/cli/log.py"),
        ],
    },
    {
        "trigger": "remind",
        "question": "有哪些明显缺失但应该有的功能？",
        "candidates": [
            ("添加 `health remind snooze <id> --hours 2` 延迟提醒命令",
             "src/services/reminder_service.py"),
            ("支持周期性提醒：`health remind add --cron '0 9 * * *'` 每天固定时间提醒",
             "src/services/reminder_service.py"),
        ],
    },
    {
        "trigger": "export",
        "question": "哪些开发者体验痛点还没被解决？",
        "candidates": [
            ("添加 `health export json --profile-id 1 --days 30` 导出原始数据供第三方使用",
             "src/services/export_service.py"),
            ("`health export summary` 支持输出 PDF 格式（通过 reportlab 或 weasyprint）",
             "src/services/export_service.py"),
        ],
    },
    {
        "trigger": "profile",
        "question": "有哪些明显缺失但应该有的功能？",
        "candidates": [
            ("添加 `health profile archive <id>` 归档不活跃 profile，减少噪音",
             "src/services/profile_service.py"),
            ("支持 `health profile switch <id>` 切换默认 profile，无需每次 --profile-id",
             "src/cli/profile.py"),
        ],
    },
    {
        "trigger": "chart",
        "question": "CLI 工具有哪些交互范式可以创新？",
        "candidates": [
            ("`health summary chart` 支持彩色输出（检测终端支持情况，自动降级）",
             "src/cli/chart.py"),
            ("添加 `health summary compare --days 7 --days 14` 对比两周数据差异",
             "src/services/summary_service.py"),
        ],
    },
    {
        "trigger": "rules",
        "question": "竞品的哪些亮点功能我们可以借鉴但还未实现？",
        "candidates": [
            ("添加饮食热量估算规则：根据 meal 事件中的食物关键词估算摄入热量，提示用户",
             "src/rules/diet_rules.py"),
            ("添加睡眠规律性规则：检测入睡时间是否稳定，波动过大给出建议",
             "src/rules/sleep_rules.py"),
        ],
    },
    {
        "trigger": "db",
        "question": "有哪些明显缺失但应该有的功能？",
        "candidates": [
            ("添加 `health db backup --path <path>` 备份数据库到指定位置",
             "src/cli/db.py"),
            ("添加 `health db stats` 显示各表记录数和数据库大小",
             "src/cli/db.py"),
        ],
    },
]

SOFTWARE_IDEA_GENERATORS_EN = [
    {
        "trigger": "cli",
        "question": "What CLI interaction paradigms could be innovated?",
        "candidates": [
            ("Add interactive `health interactive` command with Q&A to guide event logging",
             "src/cli/interactive.py"),
            ("Add `--dry-run` to `health log` to preview parsing before committing",
             "src/cli/log.py"),
            ("Support `health check --format table|json|markdown` for multi-format output",
             "src/cli/check.py"),
        ],
    },
    {
        "trigger": "advisor",
        "question": "What competitor features could we adopt?",
        "candidates": [
            ("Add plan execution tracking panel for `health advisor` showing status of each recommendation",
             "src/services/health_advisor_service.py"),
            ("Support `health advisor plan --goal <description>` for goal-based plan generation",
             "src/services/health_advisor_service.py"),
        ],
    },
    {
        "trigger": "summary",
        "question": "What developer-experience pain points remain unsolved?",
        "candidates": [
            ("Add `health summary digest --days 7` to surface the most important weekly changes and signals",
             "src/services/summary_service.py"),
            ("`health status` shows ASCII art trend charts for the last 7 days of key metrics",
             "src/cli/status.py"),
        ],
    },
    {
        "trigger": "log",
        "question": "What CLI interaction paradigms could be innovated?",
        "candidates": [
            ("Support batch import via CSV/JSON for bulk historical event entry",
             "src/cli/log.py"),
            ("Add `health log edit <event-id>` to correct previously logged events",
             "src/cli/log.py"),
        ],
    },
    {
        "trigger": "remind",
        "question": "What obviously missing features should exist?",
        "candidates": [
            ("Add `health remind snooze <id> --hours 2` to defer a reminder",
             "src/services/reminder_service.py"),
            ("Support cron-style recurring reminders: `health remind add --cron '0 9 * * *'`",
             "src/services/reminder_service.py"),
        ],
    },
    {
        "trigger": "export",
        "question": "What developer-experience pain points remain unsolved?",
        "candidates": [
            ("Add `health export json --profile-id 1 --days 30` for raw data export",
             "src/services/export_service.py"),
            ("`health export summary` supports PDF output via reportlab or weasyprint",
             "src/services/export_service.py"),
        ],
    },
]

GENERIC_GENERATORS_ZH = [
    {
        "trigger": "general",
        "question": "这个项目最影响使用体验的问题是什么？",
        "candidates": [
            ("审视项目，找出用户抱怨最多或最影响工作效率的一个具体问题，优先修复",
             ""),
        ],
    },
    {
        "trigger": "general",
        "question": "有没有明显缺失但应该有的功能？",
        "candidates": [
            ("审视项目结构和用户旅程，找出使用路径中最大的断点，添加对应功能",
             ""),
        ],
    },
]

# ── Core logic ─────────────────────────────────────────────────────────────

def _load_inspire_questions(project_md_path: Path, language: str) -> list[str]:
    """Read inspire questions from PROJECT.md."""
    if not project_md_path.exists():
        return SOFTWARE_ZH if language == "zh" else SOFTWARE_EN

    text = project_md_path.read_text(encoding="utf-8", errors="ignore")
    # Extract the "开放方向（{kind} 类 inspire 问题）" section
    m = re.search(r"##\s*开放方向[^#]*##", text, re.DOTALL)
    if not m:
        return SOFTWARE_ZH if language == "zh" else SOFTWARE_EN

    block = m.group(0)
    lines = block.splitlines()
    questions = []
    for line in lines:
        # Numbered list items like "1. 问题内容"
        nm = re.match(r"^\s*\d+[.．]\s*(.+)", line)
        if nm:
            questions.append(nm.group(1).strip())
    return questions if questions else (SOFTWARE_ZH if language == "zh" else SOFTWARE_EN)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _sanitize_cell(text: str) -> str:
    return text.replace("|", "/").replace("\n", " ").strip()


def _src_package_roots(project: Path) -> list[Path]:
    roots = [project]
    src_root = project / "src"
    if src_root.exists():
        roots.append(src_root)
        for child in src_root.iterdir():
            if child.is_dir() and not child.name.endswith(".egg-info"):
                roots.append(child)
    return roots


def _candidate_paths(project: Path, file_hint: str) -> list[Path]:
    hint = file_hint.strip()
    if not hint:
        return []

    paths: list[Path] = [project / hint]
    if hint.startswith("src/"):
        suffix = hint[len("src/"):]
        for root in _src_package_roots(project):
            paths.append(root / suffix)
    return paths


def _candidate_relevant(project: Path, file_hint: str) -> bool:
    if not file_hint:
        return True

    for path in _candidate_paths(project, file_hint):
        if path.exists():
            return True
        if path.parent.exists():
            return True
    return False


def _read_queue_rows(heartbeat_path: Path) -> list[dict[str, str]]:
    if not heartbeat_path.exists():
        return []
    return _parse_all_queue_rows(heartbeat_path.read_text(encoding="utf-8", errors="ignore"))


def _write_queue_rows(heartbeat_path: Path, rows: list[dict[str, str]]) -> None:
    content = heartbeat_path.read_text(encoding="utf-8", errors="ignore")
    new_block = _render_queue_block(rows)
    heartbeat_path.write_text(_replace_all_queue_sections(content, new_block), encoding="utf-8")


def _detect_existing_queue_content(heartbeat_path: Path) -> set[str]:
    """Collect all normalized idea/improve content from Queue AND Done Log AND Run Status.

    Dedup covers:
    - Queue (pending items not yet executed)
    - Done Log (items already completed)
    - Run Status last_generated_content (prevents re-generation on consecutive a-refresh)
    """
    seen: set[str] = set()
    for row in _read_queue_rows(heartbeat_path):
        seen.add(_normalize_text(row.get("content", "")))
    # Skip ideas already completed (in Done Log)
    text = heartbeat_path.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"## Done Log\b[\s\S]*?\| Time \| Commit \| Task \| Result \|[\s\S]*?(?=\n## |\Z)", text)
    if m:
        rows = re.findall(r"\|\s*\d{4}-\d{2}-\d{2}[^|]*?\s*\|\s*`?[a-f0-9]+`?\s*\|\s*([^|]+?)\s*\|", m.group(0))
        for task in rows:
            seen.add(_normalize_text(task.strip()))
    # Skip last generated item (prevents re-generation on consecutive a-refresh)
    last_norm = _get_last_generated_content(heartbeat_path)
    if last_norm:
        seen.add(last_norm)
    return seen


def _generate_ideas_for_software(
    project: Path, language: str, seen: set[str]
) -> list[tuple[str, str, int]]:
    """Generate concrete [[Idea]] tasks for a software project."""
    generators = (
        SOFTWARE_IDEA_GENERATORS_ZH if language == "zh"
        else SOFTWARE_IDEA_GENERATORS_EN
    )
    results: list[tuple[str, str, int]] = []

    for gen in generators:
        for idea_text, file_hint in gen["candidates"]:
            norm = _normalize_text(idea_text)
            if norm in seen:
                continue
            if not _candidate_relevant(project, file_hint):
                continue
            results.append((idea_text, gen["question"], 62))
            seen.add(norm)
            break

    # If we didn't find enough, fall back to generic ones
    if len(results) < 3:
        for gen in GENERIC_GENERATORS_ZH:
            for idea_text, _question in gen["candidates"]:
                norm = _normalize_text(idea_text)
                if norm not in seen:
                    results.append((idea_text, gen["question"], 45))
                    seen.add(norm)

    return results[:3]


def _write_ideas_to_heartbeat(
    heartbeat_path: Path,
    ideas: list[tuple[str, str, int]],
    language: str,
) -> int:
    """Append [[Idea]] rows to the Queue table. Returns count written."""
    if not ideas:
        return 0

    rows = _read_queue_rows(heartbeat_path)
    existing = {_normalize_text(row.get("content", "")) for row in rows}
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    added = 0

    for idea_text, question, score in ideas:
        norm = _normalize_text(idea_text)
        if norm in existing:
            continue
        rows.append(
            {
                "type": "idea",
                "score": str(score),
                "content": _sanitize_cell(f"[[Idea]] {idea_text}"),
                "detail": _sanitize_cell(idea_text),
                "source": _sanitize_cell(f"inspire: {question}"),
                "status": "pending",
                "created": created,
            }
        )
        existing.add(norm)
        added += 1

    if added:
        rows.sort(
            key=lambda r: (
                0 if r.get("status", "").strip().lower() == "pending" else 1,
                -int(r.get("score", "0") or 0),
                r.get("created", ""),
            )
        )
        _write_queue_rows(heartbeat_path, rows)
    return added


def _read_done_log_tasks(heartbeat_path: Path) -> list[str]:
    if not heartbeat_path.exists():
        return []
    text = heartbeat_path.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"## Done Log\b[\s\S]*?\| Time \| Commit \| Task \| Result \|[\s\S]*?(?=\n## |\Z)", text)
    if not m:
        return []
    return [task.strip() for task in re.findall(r"\|\s*\d{4}-\d{2}-\d{2}[^|]*?\s*\|\s*`?[a-f0-9]+`?\s*\|\s*([^|]+?)\s*\|", m.group(0))]


def _count_trailing_improves_since_last_idea(heartbeat_path: Path) -> int:
    count = 0
    for task in reversed(_read_done_log_tasks(heartbeat_path)):
        if "[[Idea]]" in task:
            return 0 if count == 0 else count
        if "[[Improve]]" in task:
            count += 1
            continue
        break
    return count


def _decide_next_type_from_state(last_type: str | None, improves_since_last_idea: int) -> str:
    if last_type is None:
        return "idea"
    if last_type == "idea":
        return "improve"
    return "idea" if improves_since_last_idea >= 2 else "improve"


def _advance_alternation_state(last_type: str | None, improves_since_last_idea: int, generated_type: str) -> tuple[str, int]:
    if generated_type == "idea":
        return "idea", 0
    next_counter = improves_since_last_idea + 1 if last_type == "improve" else 1
    return "improve", next_counter


def _build_candidates_for_type(
    project: Path,
    kind: str,
    language: str,
    seen: set[str],
    task_type: str,
) -> list[tuple[str, str, int]]:
    if task_type == "idea":
        if kind == "software":
            return _generate_ideas_for_software(project, language, seen)
        project_md = project / "PROJECT.md"
        if not project_md.exists():
            project_md = SKILL_DIR / "PROJECT.md"
        questions = _load_inspire_questions(project_md, language)
        results: list[tuple[str, str, int]] = []
        for i in range(min(3, len(questions))):
            question = questions[i % len(questions)]
            text = (
                f"基于问题「{question}」审视项目，找到最值得改进的地方并实施"
                if language == "zh"
                else f"Review the project through the question '{question}' and implement the most worthwhile improvement"
            )
            norm = _normalize_text(text)
            if norm in seen:
                continue
            results.append((text, question, 45))
            seen.add(norm)
        return results

    generator = IMPROVE_GENERATORS.get(kind, IMPROVE_GENERATORS["generic"])
    candidates = generator(project, language, seen)
    if candidates or kind == "generic":
        return candidates
    return IMPROVE_GENERATORS["generic"](project, language, seen)


def refresh_inspire_queue(
    project: Path,
    heartbeat: Path | None = None,
    *,
    language: str = "zh",
    target_size: int = 6,
) -> dict:
    """Refresh queue to a full rolling backlog with a 2 Improve : 1 Idea ratio.

    Keeps user-authored rows, rebuilds non-user rows from current project state,
    and generates the next `target_size` tasks in alternation order based on the
    latest Done Log state.
    """
    heartbeat = heartbeat or HEARTBEAT
    project = project.expanduser().resolve()
    kind = _detect_project_type(project)
    existing_rows = _read_queue_rows(heartbeat)
    user_rows = [row for row in existing_rows if row.get("type", "").strip().lower() == "user"]

    seen: set[str] = {_normalize_text(row.get("content", "")) for row in user_rows}
    seen.update(_normalize_text(task) for task in _read_done_log_tasks(heartbeat))

    last_type = _get_last_done_type(heartbeat)
    counter = _count_trailing_improves_since_last_idea(heartbeat)
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    generated_rows: list[dict[str, str]] = []
    generated_types: list[str] = []

    for _ in range(max(target_size, 0)):
        next_type = _decide_next_type_from_state(last_type, counter)
        candidates = _build_candidates_for_type(project, kind, language, set(seen), next_type)
        if not candidates:
            alt_type = "improve" if next_type == "idea" else "idea"
            candidates = _build_candidates_for_type(project, kind, language, set(seen), alt_type)
            if not candidates:
                break
            next_type = alt_type

        best_text, best_detail, best_score = max(candidates, key=lambda x: x[2])
        source = f"inspire: {best_detail}" if next_type == "idea" else "rolling-refresh"
        prefix = "[[Idea]]" if next_type == "idea" else "[[Improve]]"
        generated_rows.append(
            {
                "type": next_type,
                "score": str(best_score),
                "content": _sanitize_cell(f"{prefix} {best_text}"),
                "detail": _sanitize_cell(best_text),
                "source": _sanitize_cell(source),
                "status": "pending",
                "created": created,
            }
        )
        seen.add(_normalize_text(best_text))
        generated_types.append(next_type)
        last_type, counter = _advance_alternation_state(last_type, counter, next_type)

    _write_queue_rows(heartbeat, user_rows + generated_rows)
    _set_improves_since_idea(heartbeat, _count_trailing_improves_since_last_idea(heartbeat))

    return {
        "generated": len(generated_rows),
        "target_size": target_size,
        "types": generated_types,
        "improves_since_last_idea": _count_trailing_improves_since_last_idea(heartbeat),
        "first": generated_rows[0]["content"] if generated_rows else "",
    }


# ── Public API ─────────────────────────────────────────────────────────────

def run_inspire_scan(
    project: Path,
    heartbeat: Path | None = None,
    *,
    language: str = "zh",
) -> dict:
    """
    Run one inspire scan cycle: decide next task type, generate candidates,
    pick the best one, and inject it into the queue.

    The task type alternates via _decide_next_type() (idea → improve → idea ...).
    Each cycle produces exactly ONE new queue row, replacing any existing row
    of the same type.

    Args:
        project: Path to the managed project.
        heartbeat: Path to HEARTBEAT.md (default: skill_dir/HEARTBEAT.md).
        language: 'zh' or 'en'.

    Returns:
        dict with keys: generated, content, score, detail, source,
                        improves_since_last_idea
    """
    heartbeat = heartbeat or HEARTBEAT
    next_type = _decide_next_type(heartbeat)
    seen = _detect_existing_queue_content(heartbeat)
    kind = _detect_project_type(project)

    # ── Generate candidates ─────────────────────────────────────────────────
    if next_type == "idea":
        if kind == "software":
            candidates = _generate_ideas_for_software(project, language, seen)
        else:
            project_md = project / "PROJECT.md"
            if not project_md.exists():
                project_md = SKILL_DIR / "PROJECT.md"
            questions = _load_inspire_questions(project_md, language)
            candidates = [
                (
                    f"基于问题「{questions[i % len(questions)]}」审视项目，找到最值得改进的地方并实施",
                    questions[i % len(questions)],
                    45,
                )
                for i in range(min(3, len(questions)))
            ]
    else:
        generator = IMPROVE_GENERATORS.get(kind, IMPROVE_GENERATORS["generic"])
        candidates = generator(project, language, seen)

    # ── No candidate found ─────────────────────────────────────────────────
    if not candidates:
        return {
            "generated": next_type,
            "content": "(no candidate)",
            "score": 0,
            "detail": "",
            "source": "",
            "improves_since_last_idea": _get_improves_since_idea(heartbeat),
        }

    # ── Pick best candidate (highest score, first if tie) ───────────────────
    best_text, best_detail, best_score = max(candidates, key=lambda x: x[2])

    # ── Set source ─────────────────────────────────────────────────────────
    if next_type == "idea":
        source = f"inspire: {best_detail}"
    else:
        activity = _get_recent_git_activity(project, n=5)
        module_name = activity[0][0] if activity else "project"
        source = f"git: {module_name}"

    # ── Build queue row ─────────────────────────────────────────────────────
    created = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    type_label = "idea" if next_type == "idea" else "improve"
    prefix = "[[Idea]]" if next_type == "idea" else "[[Improve]]"
    new_row = {
        "type": type_label,
        "score": str(best_score),
        "content": _sanitize_cell(f"{prefix} {best_text}"),
        "detail": _sanitize_cell(best_text),
        "source": _sanitize_cell(source),
        "status": "pending",
        "created": created,
    }

    # ── Read, replace same-type rows, append, sort, write ──────────────────
    rows = _read_queue_rows(heartbeat)
    rows = [r for r in rows if r.get("type", "").strip().lower() != next_type]
    rows.append(new_row)
    rows.sort(
        key=lambda r: (
            0 if r.get("status", "").strip().lower() == "pending" else 1,
            -int(r.get("score", "0") or 0),
            r.get("created", ""),
        )
    )
    _write_queue_rows(heartbeat, rows)

    # ── Update alternation counter in Run Status ──────────────────────────
    # Counter = how many improves have been GENERATED since last idea.
    # Increment AFTER generation so the NEXT _decide_next_type call sees
    # the correct count and flips at exactly 2.
    #
    # Semantics per cycle:
    #   - Generate idea → counter=0 (new streak starts; next call sees
    #     last_type=idea → improve, counter stays 0)
    #   - Generate improve → counter=1 (one improve in flight; next call
    #     sees last_type=improve, counter bumps to 2 → flip to idea)
    #
    # Ratio: 2 improves per idea ✓
    current = _get_improves_since_idea(heartbeat)
    new_counter = (current + 1) if next_type == "improve" else 0
    _set_improves_since_idea(heartbeat, new_counter)
    _set_last_generated_content(heartbeat, best_text)

    return {
        "generated": next_type,
        "content": best_text,
        "score": best_score,
        "detail": best_detail,
        "source": source,
        "improves_since_last_idea": new_counter,
    }


# ── CLI ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Generate functional improvement ideas from inspire questions"
    )
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--heartbeat", default=None, type=Path)
    parser.add_argument("--language", default="zh", choices=["zh", "en"])
    parser.add_argument("--target-size", default=1, type=int)
    args = parser.parse_args()

    import json
    if args.target_size > 1:
        result = refresh_inspire_queue(
            project=args.project,
            heartbeat=args.heartbeat,
            language=args.language,
            target_size=args.target_size,
        )
    else:
        result = run_inspire_scan(
            project=args.project,
            heartbeat=args.heartbeat,
            language=args.language,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
