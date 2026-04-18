#!/usr/bin/env python3
"""Scan any project and append improvement candidates to HEARTBEAT.md.

This is the core "eyes" of the improvement loop. It auto-detects the project
type and generates relevant, actionable improvement ideas — regardless of whether
the project is software, a novel, a video script, or a research paper.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PROJECT TYPES & THEIR BUCKETS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

software  → test, doc, todo, ux, feature, data, engage
writing    → plot, character, pace, dialogue, structure, clarity
video      → script, pacing, visual, continuity, audio, edit
research   → structure, citation, clarity, method, conclusion
generic    → structure, clarity, consistency, completeness

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
USAGE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Scan once and append ONE best candidate
python project_insights.py --project . --heartbeat HEARTBEAT.md --language en

# Keep scanning until queue has at least N items
python project_insights.py --project . --heartbeat HEARTBEAT.md --language en --refresh --min 5
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime, timezone
from pathlib import Path


# ── Project type detection ─────────────────────────────────────────────────────

def detect_project_type(project: Path) -> str:
    """Return: software | writing | video | research | generic"""
    all_files = [f.name.lower() for f in project.rglob("*") if f.is_file()]
    all_dirs = {d.name.lower() for d in project.rglob("*") if d.is_dir()}

    software_indicators = {
        "src", "lib", "app", "packages",
        "tests", "test", "__pycache__",
        "package.json", "cargo.toml", "go.mod", "go.sum",
        "pyproject.toml", "setup.py", "requirements.txt",
        "pom.xml", "build.gradle", "Gemfile",
    }
    software_score = sum(1 for i in software_indicators if i in all_files or i in all_dirs)
    if software_score >= 2:
        return "software"

    writing_indicators = {
        "chapters", "chapter", "scenes", "scene",
        "manuscript", "characters", "outline", "drafts",
    }
    md_count = sum(1 for f in all_files if f.endswith(".md") and "readme" not in f)
    writing_score = sum(1 for i in writing_indicators if i in all_dirs) + (1 if md_count >= 5 else 0)
    if writing_score >= 2 or md_count >= 10:
        return "writing"

    video_indicators = {
        "scripts", "scenes", "storyboard", "footage",
        "shots", "sequences", "edit", "cuts", "assets",
    }
    video_score = sum(1 for i in video_indicators if i in all_dirs)
    if video_score >= 2:
        return "video"

    research_indicators = {
        "papers", "references", "bib", "tex",
        "citations", "notes", "journal", "figures",
    }
    research_score = sum(1 for i in research_indicators if i in all_dirs)
    if research_score >= 1 and any(f.endswith(".tex") or "bib" in f for f in all_files):
        return "research"

    return "generic"


# ── Buckets per project type ──────────────────────────────────────────────────

def _software_buckets(lang: str):
    en = lang == "en"
    return [
        ("test", [
            "Add unit tests for each untested module" if en else "为每个未测试的模块补齐单元测试",
            "Increase test coverage for edge cases" if en else "为边界情况增加测试覆盖",
            "Add integration tests for critical user flows" if en else "为关键用户流程增加集成测试",
            "Ensure all error paths have corresponding tests" if en else "确保所有错误路径都有对应测试",
        ]),
        ("doc", [
            "Add module-level docstrings to undocumented modules" if en else "为未写文档的模块补充 docstring",
            "Document public API contracts with usage examples" if en else "为公开 API 写清合约和使用示例",
            "Add inline comments explaining non-obvious logic" if en else "为不直观逻辑增加注释说明",
        ]),
        ("todo", [
            "Address all TODO/FIXME comments in the codebase" if en else "处理代码库中的所有 TODO/FIXME",
            "Audit deprecated code paths and remove or document them" if en else "审查并移除或标注废弃代码路径",
        ]),
        ("ux", [
            "Improve error messages: show the cause and a suggested fix" if en else "改进错误提示：给出原因和修复建议",
            "Add a verbose mode (--verbose) for detailed execution info" if en else "增加 verbose 模式（--verbose）输出详细信息",
            "Add shell completions (bash/zsh/fish) for the CLI" if en else "为 CLI 增加 shell 自动补全（bash/zsh/fish）",
            "Add a config file (~/.myapp.yaml) for user preferences" if en else "增加配置文件（~/.myapp.yaml）支持用户偏好设置",
        ]),
        ("feature", [
            "Identify the most requested unimplemented feature and add it" if en else "找出最被期待但未实现的功能并实现",
            "Add a status command showing current project state at a glance" if en else "增加 status 命令：一览当前项目状态",
        ]),
        ("data", [
            "Add an export command for structured data output" if en else "增加 export 命令输出结构化数据",
            "Add a backup/restore mechanism for project data" if en else "增加项目数据的备份/恢复机制",
        ]),
        ("engage", [
            "Add an achievement or milestone system to reward consistency" if en else "增加成就/里程碑系统，奖励持续投入",
            "Add a streak tracker for consecutive days of work" if en else "增加连续记录追踪，激励保持节奏",
        ]),
    ]


def _writing_buckets(lang: str):
    en = lang == "en"
    return [
        ("plot", [
            "Review plot consistency: check for timeline contradictions" if en else "审查情节一致性：检查时间线矛盾",
            "Identify and resolve any unresolved plot threads from earlier chapters" if en else "找出并解决早期章节遗留的未解情节线索",
            "Strengthen the central conflict: does it sustain through the middle?" if en else "强化核心冲突：是否能撑过中段？",
            "Review chapter hooks: does each chapter end with tension?" if en else "审查章节钩子：每个章节结尾是否有悬念？",
        ]),
        ("character", [
            "Review character voice consistency: does each character sound distinct?" if en else "审查角色声音一致性：每个角色是否有独特语言风格？",
            "Audit character motivations: does each major choice stem from established desire/fear?" if en else "审查角色动机：每个重大选择是否源于已有欲望或恐惧？",
            "Review secondary character arcs: do they change by the end?" if en else "审查次要角色弧线：他们最终有改变吗？",
        ]),
        ("pace", [
            "Identify the slowest 20% of scenes: can they be cut or tightened?" if en else "找出最拖沓的 20% 场景：能否精简？",
            "Review the 'sagging middle': is the middle third compelling?" if en else "审查'塌陷中部'：中段三分之一是否吸引？",
            "Check that the opening chapter hooks immediately" if en else "检查开头章节是否立刻抓住读者",
        ]),
        ("dialogue", [
            "Read each chapter's dialogue aloud: does it sound natural?" if en else "朗读每章对话：听起来自然吗？",
            "Replace generic dialogue with character-specific voice" if en else "用角色特有的声音替换通用对话",
        ]),
        ("structure", [
            "Check that each scene has a clear objective, conflict, and outcome" if en else "检查每个场景是否有清晰的目标、冲突和结果",
            "Identify scenes that could be combined or cut entirely" if en else "找出可以合并或完全删除的场景",
        ]),
        ("clarity", [
            "Replace telling with showing: find instances of summary rather than scene" if en else "把叙述换成展示：找出概括而非场景化的段落",
            "Check that each paragraph has a clear controlling idea" if en else "检查每个段落是否有清晰的中心思想",
        ]),
    ]


def _video_buckets(lang: str):
    en = lang == "en"
    return [
        ("script", [
            "Review scene objectives: does each scene have a clear purpose?" if en else "审查场景目标：每个场景是否有清晰目的？",
            "Review the cold open: does it hook in the first 30 seconds?" if en else "审查开头：前 30 秒是否抓住观众？",
            "Add camera direction notes to action scenes" if en else "为动作场景增加摄影指导备注",
        ]),
        ("pacing", [
            "Map the emotional arc beat-by-beat: is there enough variation?" if en else "逐 Beat 地图情感弧线：变化够吗？",
            "Review the runtime: does it match the intended format/length?" if en else "审查时长：是否符合目标格式/长度？",
        ]),
        ("visual", [
            "Review shot list for visual variety: avoid repetitive shot types" if en else "审查镜头表：避免重复的镜头类型",
            "Check that key visual moments are staged for maximum impact" if en else "检查关键视觉时刻是否被设计得最具冲击力",
        ]),
        ("continuity", [
            "Create a continuity log for props, costumes, and set elements" if en else "为道具、服装和布景元素建立连续性日志",
            "Review timeline consistency: do time-of-day cues stay coherent?" if en else "审查时间线一致性：日夜线索是否连贯？",
        ]),
        ("audio", [
            "Review audio cue placement: do sound effects support the visuals?" if en else "审查音效cue位置：音效是否配合画面？",
            "Check that music choices reinforce the emotional tone" if en else "检查音乐选择是否强化情感基调",
        ]),
        ("edit", [
            "Review cuts: do they feel motivated or arbitrary?" if en else "审查切换：是有动机还是随意？",
            "Review the final 30 seconds: does it end with impact?" if en else "审查最后 30 秒：是否有冲击力结尾？",
        ]),
    ]


def _research_buckets(lang: str):
    en = lang == "en"
    return [
        ("structure", [
            "Verify the paper structure: abstract → intro → method → results → discussion" if en else "核查论文结构：摘要→引言→方法→结果→讨论",
            "Ensure the abstract is self-contained and summaries all sections" if en else "确保摘要独立完整，概括所有部分",
        ]),
        ("citation", [
            "Add missing citations: check for uncited references and unlisted sources" if en else "补充遗漏引用：检查未引用的参考文献和未列出来源",
            "Ensure citations are up-to-date: add recent related work" if en else "确保引用最新：补充近年相关工作",
            "Check that all figures and tables are cited in the text" if en else "检查所有图表是否在正文中被引用",
        ]),
        ("clarity", [
            "Replace jargon with accessible language where possible" if en else "在可能的地方用通俗语言替换术语",
            "Check that all abbreviations are defined on first use" if en else "检查所有缩写是否在首次使用时定义",
        ]),
        ("method", [
            "Verify methodology is described in enough detail to reproduce" if en else "核实方法论描述足够详细，可复现",
            "Check that limitations are acknowledged transparently" if en else "检查局限性是否被透明承认",
        ]),
        ("conclusion", [
            "Verify that conclusions are supported by the data presented" if en else "核实结论由所呈数据支撑",
            "Check that implications are discussed without overgeneralizing" if en else "检查是否讨论意义而不过度泛化",
        ]),
    ]


def _generic_buckets(lang: str):
    en = lang == "en"
    return [
        ("structure", [
            "Review overall project structure: is the hierarchy logical and navigable?" if en else "审查整体项目结构：层次是否逻辑清晰？",
            "Identify any orphaned or unlinked content that should be integrated" if en else "找出孤立或未链接的内容，应整合",
        ]),
        ("clarity", [
            "Audit terminology consistency across all documents" if en else "审查所有文档的术语一致性",
            "Review any ambiguous or vague statements and make them precise" if en else "审查模糊陈述，使其精确",
        ]),
        ("consistency", [
            "Check naming conventions: are they applied uniformly?" if en else "检查命名规范：是否统一应用？",
            "Review tone and voice: is it consistent throughout?" if en else "审查语气和风格：全文一致吗？",
        ]),
        ("completeness", [
            "Identify sections that end abruptly and need development" if en else "找出戛然而止的章节，需要充实",
            "Review the outline: are there gaps in coverage?" if en else "审查大纲：覆盖是否有空白？",
        ]),
        ("workflow", [
            "Identify manual steps that could be automated or templated" if en else "找出可以自动化或模板化的手动步骤",
            "Check that key decisions and their rationale are documented" if en else "检查关键决策和理由是否被记录",
        ]),
    ]


def get_buckets(project_type: str, lang: str):
    return {
        "software": _software_buckets,
        "writing": _writing_buckets,
        "video": _video_buckets,
        "research": _research_buckets,
        "generic": _generic_buckets,
    }[project_type](lang)


# ── Core queue logic ──────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    return re.sub(r'\s+', ' ', text.strip())


def _strip_prefix(content: str) -> str:
    content = re.sub(r'^\[\[[^\]]+\]\]\s*score=\d+\s*\|\s*', '', content).strip()
    content = re.sub(r'^\[\[[^\]]+\]\]\s*', '', content).strip()
    return content


def _table_cell(line: str, col: int) -> str:
    cells = [c.strip() for c in line.split('|')]
    return cells[col + 1] if col + 1 < len(cells) else ''


def existing_queue_normalized(heartbeat: Path) -> set[str]:
    """Normalized content strings already in the queue."""
    content = heartbeat.read_text(encoding="utf-8")
    seen: set[str] = set()
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith('|') or stripped.startswith('|---'):
            continue
        if not re.match(r'^\|\s*(\d+)\s*\|', stripped):
            continue
        cell4 = _table_cell(stripped, 3)
        seen.add(_normalize(_strip_prefix(cell4)).lower())
    return seen


def choose_best_candidate(project: Path, heartbeat: Path, lang: str) -> str | None:
    """Return the highest-priority new idea from all buckets."""
    ptype = detect_project_type(project)
    existing = existing_queue_normalized(heartbeat)
    for _bucket_name, ideas in get_buckets(ptype, lang):
        for idea in ideas:
            if _normalize(idea).lower() not in existing:
                return idea
    return None


def score_finding(finding: str) -> int:
    fl = finding.lower()
    if any(k in fl for k in ['单元测试', '补齐', 'missing', 'undocumented']):
        return 50
    if any(k in fl for k in ['docstring', 'document', '文档', 'comment']):
        return 45
    if any(k in fl for k in ['plot', 'character', 'pacing', 'pace', '情节', '角色', '节奏', 'voice']):
        return 65
    if any(k in fl for k in ['script', 'scene', 'shot', 'transition', '镜头', '场景', '脚本']):
        return 65
    if any(k in fl for k in ['citation', 'cite', 'reference', '引用', '文献']):
        return 65
    if any(k in fl for k in ['insight', '智能', 'predict', 'detect', '检测']):
        return 72
    if any(k in fl for k in ['export', 'import', 'backup', '导入', '导出']):
        return 65
    if any(k in fl for k in ['achievement', 'streak', '成就', '连续', 'milestone']):
        return 68
    if any(k in fl for k in ['suggest', 'compare', 'undo', 'wizard', '建议', '撤销', '对比']):
        return 70
    if any(k in fl for k in ['error', 'verbose', 'config', 'confirm', '错误', '详细']):
        return 55
    if any(k in fl for k in ['structure', 'consistency', 'completeness', '结构', '一致', '完整']):
        return 60
    return 60


def append_to_queue(heartbeat: Path, finding: str) -> bool:
    content = heartbeat.read_text(encoding="utf-8")
    section_match = re.search(r'(## Queue\n\n)([\s\S]*?)(\n---\n)', content)
    if not section_match:
        print("ERROR: Queue section not found in HEARTBEAT.md", file=sys.stderr)
        return False

    score = score_finding(finding)
    section_body = section_match.group(2)
    numbers = [int(m) for m in re.findall(r'^\|\s*(\d+)\s*\|', section_body, re.MULTILINE)]
    next_num = max(numbers) + 1 if numbers else 1
    created = datetime.now(timezone.utc).strftime('%Y-%m-%d')

    new_line = f"| {next_num} | improve | {score} | [[Improve]] {finding} | scanner | pending | {created} |"
    new_section = (
        section_match.group(1)
        + section_body.rstrip()
        + "\n"
        + new_line
        + "\n"
        + section_match.group(3)
    )
    updated = (
        content[:section_match.start()]
        + new_section
        + content[section_match.end():]
    )
    heartbeat.write_text(updated, encoding="utf-8")
    print(f"project_insights: +1 -> {new_line}")
    return True


def queue_count(heartbeat: Path) -> int:
    content = heartbeat.read_text(encoding="utf-8")
    count = 0
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped.startswith('|') or stripped.startswith('|---'):
            continue
        if not re.match(r'^\|\s*(\d+)\s*\|', stripped):
            continue
        cells = [c.strip() for c in stripped.split('|')]
        if len(cells) >= 7 and 'pending' in cells[6].lower():
            count += 1
    return count


def refresh_queue(project: Path, heartbeat: Path, lang: str, min_items: int) -> int:
    added = 0
    max_add = max(min_items * 3, 20)
    while queue_count(heartbeat) < min_items and added < max_add:
        candidate = choose_best_candidate(project, heartbeat, lang)
        if not candidate:
            print(f"project_insights: no more candidates, queue has {queue_count(heartbeat)} pending")
            break
        if append_to_queue(heartbeat, candidate):
            added += 1
    if added >= max_add and queue_count(heartbeat) < min_items:
        print(f"project_insights: safety stop after {added} additions; pending={queue_count(heartbeat)}")
    if added:
        print(f"project_insights: added {added} items (total pending: {queue_count(heartbeat)})")
    return added


# ── CLI ────────────────────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Discover improvement opportunities for any project type. "
        "Auto-detects: software, writing, video, research, generic."
    )
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--heartbeat", required=True, type=Path)
    parser.add_argument("--language", default="en", choices=["en", "zh"])
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--min", type=int, default=5)
    args = parser.parse_args()

    if not args.heartbeat.exists():
        print(f"ERROR: HEARTBEAT not found: {args.heartbeat}", file=sys.stderr)
        return 1

    ptype = detect_project_type(args.project.resolve())
    print(f"[project_insights] type={ptype} lang={args.language}")

    if args.refresh:
        added = refresh_queue(args.project.resolve(), args.heartbeat.resolve(), args.language, args.min)
        return 0 if added >= 0 else 1

    candidate = choose_best_candidate(args.project.resolve(), args.heartbeat.resolve(), args.language)
    if not candidate:
        print("project_insights: no new candidates found")
        return 0
    return 0 if append_to_queue(args.heartbeat.resolve(), candidate) else 1


if __name__ == "__main__":
    raise SystemExit(main())
