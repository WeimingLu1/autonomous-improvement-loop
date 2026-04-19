#!/usr/bin/env python3
"""
inspire_scanner.py — generate functional improvement ideas from PROJECT.md inspire questions.

Runs AFTER update_heartbeat normal queue refresh. Every N calls (tracked via
HEARTBEAT Run Status), this module reads the inspire questions from PROJECT.md,
analyses the current project state, and injects concrete [[Idea]] tasks into HEARTBEAT.

Unlike the [[Improve]] scanner (which finds explicit tag markers in code),
inspire_scanner uses the project-type + inspire questions to REASON about
gaps that no one has tagged yet — real new features, not just "add more tests".

Usage:
    from inspire_scanner import run_inspire_scan
    run_inspire_scan(project, heartbeat, language, every_n=5)
"""
from __future__ import annotations

import re
import argparse
from pathlib import Path
from datetime import datetime, timezone

from project_insights import _parse_all_queue_rows, _render_queue_block, _replace_all_queue_sections

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
    seen: set[str] = set()
    for row in _read_queue_rows(heartbeat_path):
        seen.add(_normalize_text(row.get("content", "")))
    return seen


def _pending_idea_count(heartbeat_path: Path) -> int:
    return sum(
        1
        for row in _read_queue_rows(heartbeat_path)
        if row.get("type", "").strip().lower() == "idea"
        and row.get("status", "").strip().lower() == "pending"
    )


def _get_inspire_cycle(heartbeat_path: Path) -> int:
    """Read inspire_scan_cycle from Run Status table row or legacy HTML comment."""
    if not heartbeat_path.exists():
        return 0
    text = heartbeat_path.read_text(encoding="utf-8", errors="ignore")
    # Try table format: | inspire_scan_cycle | N |
    m = re.search(r"\|\s*inspire_scan_cycle\s*\|\s*(\d+)\s*\|", text)
    if m:
        return int(m.group(1))
    # Legacy HTML comment format
    m = re.search(r"<!--\s*inspire_scan_cycle:\s*(\d+)\s*-->", text)
    if m:
        return int(m.group(1))
    return 0


def _set_inspire_cycle(heartbeat_path: Path, cycle: int) -> None:
    if not heartbeat_path.exists():
        return
    text = heartbeat_path.read_text(encoding="utf-8", errors="ignore")

    # 1. Remove legacy HTML comment if present
    text = re.sub(r"<!--\s*inspire_scan_cycle:\s*\d+\s*-->\s*", "", text)

    # 2. Remove legacy plain-text 'inspire_scan_cycle : N' line (outside table)
    text = re.sub(r'\ninspire_scan_cycle\s*:\s*\d+\s*\n', '\n', text)

    # 3. Update or insert table row | inspire_scan_cycle | N |
    cycle_row = f'| inspire_scan_cycle | {cycle} |'
    if re.search(r'\|\s*inspire_scan_cycle\s*\|\s*\d+\s*\|', text):
        text = re.sub(r'(\|\s*inspire_scan_cycle\s*\|\s*)\d+(\s*\|)', rf'\g<1>{cycle}\g<2>', text, count=1)
    elif '## Run Status' in text:
        import re as _re
        m = _re.search(r'(\|| Field | Value |\n\|-------+------+\|\n)', text)
        if m:
            text = text[:m.end()] + cycle_row + '\n' + text[m.end():]
    heartbeat_path.write_text(text, encoding='utf-8')
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


# ── Public API ─────────────────────────────────────────────────────────────

def run_inspire_scan(
    project: Path,
    heartbeat: Path | None = None,
    *,
    language: str = "zh",
    every_n: int = 5,
) -> dict:
    """
    Run inspire scan and inject new ideas into HEARTBEAT.

    Args:
        project: Path to the managed project.
        heartbeat: Path to HEARTBEAT.md (default: skill_dir/HEARTBEAT.md).
        language: 'zh' or 'en'.
        every_n: How often to actually inject (every_n calls = one real injection).
                 Controlled externally via the cycle_count in HEARTBEAT Run Status.

    Returns:
        dict with keys: injected (int), skipped (str), cycle (int)
    """
    heartbeat = heartbeat or HEARTBEAT
    project_md = project / "PROJECT.md"
    if not project_md.exists():
        project_md = SKILL_DIR / "PROJECT.md"

    cycle_count = _get_inspire_cycle(heartbeat)
    new_cycle = cycle_count + 1
    _set_inspire_cycle(heartbeat, new_cycle)
    should_inject = new_cycle % every_n == 0

    if not should_inject:
        return {
            "injected": 0,
            "skipped": f"cycle {new_cycle}/{every_n} (injects every {every_n} cycles)",
            "cycle": new_cycle,
        }

    if _pending_idea_count(heartbeat) >= 2:
        return {
            "injected": 0,
            "skipped": "pending idea items already exist",
            "cycle": new_cycle,
        }

    # Actually generate and inject ideas
    seen = _detect_existing_queue_content(heartbeat)
    project_md_text = project_md.read_text(encoding="utf-8", errors="ignore") if project_md.exists() else ""
    kind_m = re.search(r"\|\s*类型\s*\|\s*(\w+)\s*\|", project_md_text)
    kind = kind_m.group(1) if kind_m else "software"

    if kind == "software":
        ideas = _generate_ideas_for_software(project, language, seen)
    else:
        questions = _load_inspire_questions(project_md, language)
        # Generic fallback
        ideas = [
            (
                f"基于问题「{questions[i % len(questions)]}」审视项目，找到最值得改进的地方并实施",
                questions[i % len(questions)],
                45,
            )
            for i in range(min(3, len(questions)))
        ]

    written = _write_ideas_to_heartbeat(heartbeat, ideas, language)

    return {
        "injected": written,
        "skipped": None,
        "cycle": new_cycle,
        "ideas": [t for t, _, _ in ideas],
    }


# ── CLI ─────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Generate functional improvement ideas from inspire questions")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--heartbeat", default=None, type=Path)
    parser.add_argument("--language", default="zh", choices=["zh", "en"])
    parser.add_argument("--every-n", default=5, type=int,
                        help="Inject ideas every N calls (default: 5)")
    args = parser.parse_args()

    import json
    result = run_inspire_scan(
        project=args.project,
        heartbeat=args.heartbeat,
        language=args.language,
        every_n=args.every_n,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())