#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".pytest_cache", "dist", "build"}


def detect_project_type(project: Path) -> str:
    names = {p.name for p in project.iterdir()} if project.exists() else set()
    if {"src", "tests"} & names or (project / "pyproject.toml").exists() or (project / "setup.py").exists():
        return "software"
    if {"chapters", "outline.md"} & names:
        return "writing"
    if {"scripts", "scenes", "storyboard"} & names:
        return "video"
    if {"papers", "references"} & names or list(project.glob("*.tex")):
        return "research"
    return "generic"


def _get_inspire_questions(kind: str, language: str) -> list[str]:
    zh = language.lower().startswith("zh")
    mapping = {
        "software": [
            "What CLI or UX change would reduce friction the most?" if not zh else "什么 CLI 或 UX 改动最能降低使用摩擦？",
            "What would make tests easier to write?" if not zh else "什么改动会让测试更容易编写？",
        ],
        "writing": [
            "What pacing issue is most visible right now?" if not zh else "当前最明显的节奏问题是什么？",
            "Which character or section needs more depth?" if not zh else "哪个角色或章节最需要补深度？",
        ],
        "video": [
            "Which scene feels slow or unclear?" if not zh else "哪个场景最拖沓或不清晰？",
            "Where can narrative continuity improve?" if not zh else "哪里可以提升叙事连续性？",
        ],
        "research": [
            "Which methodology gap is most important?" if not zh else "当前最重要的方法论缺口是什么？",
            "What counterargument or citation is missing?" if not zh else "缺少什么反驳观点或引用？",
        ],
        "generic": [
            "What improvement would make this project easier to maintain?" if not zh else "什么改动会让这个项目更易维护？",
            "What small improvement would create the most leverage?" if not zh else "什么小改动会带来最大的杠杆收益？",
        ],
    }
    return mapping.get(kind, mapping["generic"])


def _walk_files(project: Path):
    for p in project.rglob("*"):
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.is_file():
            yield p


def detect_repo(project: Path) -> str:
    git_config = project / ".git" / "config"
    if not git_config.exists():
        return "—"
    text = git_config.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"url\s*=\s*(.+)", text)
    if not m:
        return "—"
    url = m.group(1).strip()
    m = re.match(r"git@github\.com:(.+?)(?:\.git)?$", url)
    if m:
        return f"https://github.com/{m.group(1)}"
    m = re.match(r"https?://github\.com/(.+?)(?:\.git)?$", url)
    if m:
        return f"https://github.com/{m.group(1)}"
    return url


def detect_version(project: Path) -> str:
    candidates = [project / "pyproject.toml", project / "setup.py", project / "VERSION"]
    candidates.extend(project.glob("src/*/__init__.py"))
    candidates.extend(project.glob("*/__init__.py"))
    for p in candidates:
        if not p.exists() or not p.is_file():
            continue
        text = p.read_text(encoding="utf-8", errors="ignore")
        if p.name == "VERSION":
            v = text.strip()
            if re.match(r"^\d+\.\d+\.\d+$", v):
                return v
        m = re.search(r"version\s*=\s*['\"](\d+\.\d+\.\d+)['\"]", text, re.I)
        if m:
            return m.group(1)
        m = re.search(r"__version__\s*=\s*['\"](\d+\.\d+\.\d+)['\"]", text, re.I)
        if m:
            return m.group(1)
    return "—"


def detect_tech_stack(project: Path, kind: str) -> str:
    # Walk once and collect all relevant data
    all_files = list(_walk_files(project))
    files = {p.name for p in all_files}
    dirs = {p.name for p in project.iterdir() if p.is_dir()} if project.exists() else set()

    # Pre-filter files by suffix to avoid repeated walking
    py_files = [p for p in all_files if p.suffix == ".py"]
    config_files = [p for p in all_files if p.suffix in {".py", ".toml", ".yaml", ".yml"}]

    # Cache file contents to avoid repeated reads
    content_cache: dict[Path, str] = {}
    def get_content(p: Path) -> str:
        if p not in content_cache:
            content_cache[p] = p.read_text(encoding="utf-8", errors="ignore").lower()
        return content_cache[p]

    stack: list[str] = []
    if kind == "software":
        if "pyproject.toml" in files or any(p.suffix == ".py" for p in all_files):
            stack.append("Python")
        if any("typer" in get_content(p) for p in py_files):
            stack.append("Typer")
        if any("sqlalchemy" in get_content(p) for p in py_files):
            stack.append("SQLAlchemy")
        if any("sqlite" in get_content(p) for p in config_files):
            stack.append("SQLite")
        if "package.json" in files:
            stack.append("Node.js")
        if not stack:
            stack.append("Software project")
    elif kind == "writing":
        stack = ["Markdown", "Long-form writing workflow"]
    elif kind == "video":
        stack = ["Script planning", "Scene/storyboard workflow"]
    elif kind == "research":
        stack = ["Research notes", "References", "Paper workflow"]
    else:
        stack = ["Structured project workspace"]
    return " + ".join(dict.fromkeys(stack))


def count_tests(project: Path) -> int:
    count = 0
    for p in _walk_files(project):
        if p.suffix == ".py":
            text = p.read_text(encoding="utf-8", errors="ignore")
            count += len(re.findall(r"^\s*def\s+test_", text, re.M))
    return count


def count_source_files(project: Path) -> int:
    return sum(1 for p in _walk_files(project) if p.suffix in {".py", ".js", ".ts", ".go", ".rs", ".java", ".md", ".tex"})


def count_cli_commands(project: Path) -> int:
    count = 0
    for p in _walk_files(project):
        if p.suffix == ".py":
            text = p.read_text(encoding="utf-8", errors="ignore")
            count += len(re.findall(r"@\w+\.command\(", text))
    return count


def summarize_snapshot(project: Path, kind: str, lang: str) -> list[tuple[str, str]]:
    if kind == "software":
        return [
            ("源码文件数" if lang == "zh" else "Source files", str(count_source_files(project))),
            ("测试用例数" if lang == "zh" else "Test cases", str(count_tests(project))),
            ("CLI 命令数" if lang == "zh" else "CLI commands", str(count_cli_commands(project))),
        ]
    if kind == "writing":
        chapters = len(list((project / "chapters").glob("*.md"))) if (project / "chapters").exists() else 0
        return [("章节数" if lang == "zh" else "Chapters", str(chapters))]
    if kind == "video":
        scenes = len(list((project / "scenes").glob("*"))) if (project / "scenes").exists() else 0
        return [("场景数" if lang == "zh" else "Scenes", str(scenes))]
    if kind == "research":
        refs = len(list((project / "references").glob("*"))) if (project / "references").exists() else 0
        return [("参考资料数" if lang == "zh" else "References", str(refs))]
    docs = len(list((project / "docs").glob("*"))) if (project / "docs").exists() else 0
    return [("文档数" if lang == "zh" else "Documents", str(docs))]


def project_positioning(name: str, kind: str, lang: str) -> str:
    if lang == "zh":
        mapping = {
            "software": f"{name} 是一个持续演进的软件项目。该文件记录项目的核心定位、当前能力与结构快照，帮助 agent 在长期自主改进时保持对项目本身的理解。",
            "writing": f"{name} 是一个持续演进的写作项目。该文件记录作品定位、结构与创作方向，帮助 agent 在长期改进时保持整体感。",
            "video": f"{name} 是一个持续演进的视频/媒体项目。该文件记录内容定位、制作结构与后续创意方向。",
            "research": f"{name} 是一个持续演进的研究项目。该文件记录研究定位、当前结构与下一步探索方向。",
            "generic": f"{name} 是一个持续演进的项目。该文件记录项目定位、当前结构与长期改进方向。",
        }
    else:
        mapping = {
            "software": f"{name} is an evolving software project. This file captures its positioning, current capabilities, and structural snapshot so the agent keeps project-level context during long-running improvement cycles.",
            "writing": f"{name} is an evolving writing project. This file captures the work's positioning, structure, and creative direction.",
            "video": f"{name} is an evolving video/media project. This file captures the content positioning, production structure, and next creative directions.",
            "research": f"{name} is an evolving research project. This file captures the research positioning, current structure, and next exploration directions.",
            "generic": f"{name} is an evolving project. This file captures the project positioning, current structure, and long-term directions.",
        }
    return mapping[kind]


def core_capabilities(project: Path, kind: str, lang: str) -> list[tuple[str, str]]:
    if kind == "software":
        caps: list[tuple[str, str]] = []
        if (project / "src").exists():
            caps.append(("源码实现" if lang == "zh" else "Source implementation", "核心业务逻辑与功能实现" if lang == "zh" else "Core business logic and feature implementation"))
        if (project / "tests").exists():
            caps.append(("测试体系" if lang == "zh" else "Test suite", "单元/集成测试覆盖关键行为与边界情况" if lang == "zh" else "Unit/integration tests covering key behaviors and edge cases"))
        if (project / "docs").exists() or (project / "README.md").exists():
            caps.append(("文档与说明" if lang == "zh" else "Docs and guidance", "项目说明、使用方式与维护知识" if lang == "zh" else "Project docs, usage guidance, and maintenance knowledge"))
        if count_cli_commands(project) > 0:
            caps.append(("CLI 接口" if lang == "zh" else "CLI surface", "命令行入口与交互命令" if lang == "zh" else "Command-line entrypoints and interactive commands"))
        return caps or [("核心能力" if lang == "zh" else "Core capability", "持续迭代的软件能力" if lang == "zh" else "Continuously evolving software capability")]
    mapping = {
        "writing": [("作品结构" if lang == "zh" else "Work structure", "章节、纲要与内容组织" if lang == "zh" else "Chapters, outline, and content organization")],
        "video": [("制作资产" if lang == "zh" else "Production assets", "脚本、场景与分镜组织" if lang == "zh" else "Scripts, scenes, and storyboard organization")],
        "research": [("研究结构" if lang == "zh" else "Research structure", "论文、参考文献与笔记组织" if lang == "zh" else "Papers, references, and notes organization")],
        "generic": [("项目材料" if lang == "zh" else "Project materials", "文档、资料与结构化工作内容" if lang == "zh" else "Docs, materials, and structured work content")],
    }
    return mapping[kind]


def architecture_block(project: Path, kind: str, lang: str) -> str:
    if kind == "software":
        parts = []
        if (project / "src").exists():
            parts.append("src/")
        if (project / "tests").exists():
            parts.append("tests/")
        if (project / "docs").exists():
            parts.append("docs/")
        joined = " / ".join(parts) if parts else "project files"
        if lang == "zh":
            return f"```\n项目根目录\n└── {joined}\n```"
        return f"```\nproject root\n└── {joined}\n```"
    if lang == "zh":
        return "```\n项目根目录\n└── 按项目类型组织内容与素材\n```"
    return "```\nproject root\n└── content organized by project type\n```"


def render_project_md(project: Path, repo: str | None = None, language: str = "zh", project_type: str | None = None) -> str:
    kind = project_type if project_type is not None else detect_project_type(project)
    repo = repo or detect_repo(project)
    version = detect_version(project)
    stack = detect_tech_stack(project, kind)
    inspires = _get_inspire_questions(kind, language)
    snapshot = summarize_snapshot(project, kind, language)
    caps = core_capabilities(project, kind, language)
    name = project.name

    if language == "zh":
        lines = [
            f"# {name} — 项目概览",
            "",
            "> 持续自主改进项目 | 由 autonomous-improvement-loop 驱动",
            "",
            "---",
            "",
            "## 基本信息",
            "",
            "| 字段 | 内容 |",
            "|------|------|",
            f"| 名称 | {name} |",
            f"| 类型 | {kind} |",
            f"| 版本 | {version} |",
            f"| 仓库 | {repo} |",
            f"| 技术栈 | {stack} |",
            "",
            "---",
            "",
            "## 当前快照",
            "",
            "| 指标 | 当前值 |",
            "|------|--------|",
        ]
        for k, v in snapshot:
            lines.append(f"| {k} | {v} |")
        lines += [
            "",
            "---",
            "",
            "## 项目定位",
            "",
            project_positioning(name, kind, language),
            "",
            "---",
            "",
            "## 核心能力",
            "",
            "| 模块 | 说明 |",
            "|------|------|",
        ]
        for k, v in caps:
            lines.append(f"| {k} | {v} |")
        lines += [
            "",
            "---",
            "",
            "## 技术结构",
            "",
            architecture_block(project, kind, language),
            "",
            "---",
            "",
            f"## 开放方向（{kind} 类 inspire 问题）",
            "",
            "以下问题用于帮助 agent 在长期改进中保持创造性视角：",
            "",
        ]
        for i, q in enumerate(inspires, 1):
            lines.append(f"{i}. {q}")
        lines.append("")
        return "\n".join(lines)

    lines = [
        f"# {name} — Project Overview",
        "",
        "> Continuous improvement project | maintained by autonomous-improvement-loop",
        "",
        "---",
        "",
        "## Basic Info",
        "",
        "| Field | Value |",
        "|------|-------|",
        f"| Name | {name} |",
        f"| Type | {kind} |",
        f"| Version | {version} |",
        f"| Repo | {repo} |",
        f"| Tech stack | {stack} |",
        "",
        "---",
        "",
        "## Current Snapshot",
        "",
        "| Metric | Value |",
        "|------|-------|",
    ]
    for k, v in snapshot:
        lines.append(f"| {k} | {v} |")
    lines += [
        "",
        "---",
        "",
        "## Positioning",
        "",
        project_positioning(name, kind, language),
        "",
        "---",
        "",
        "## Core Capabilities",
        "",
        "| Area | Description |",
        "|------|-------------|",
    ]
    for k, v in caps:
        lines.append(f"| {k} | {v} |")
    lines += [
        "",
        "---",
        "",
        "## Structure",
        "",
        architecture_block(project, kind, language),
        "",
        "---",
        "",
        f"## Open Directions ({kind} inspire prompts)",
        "",
        "These questions help the agent keep a creative, project-level perspective during long-running improvement cycles:",
        "",
    ]
    for i, q in enumerate(inspires, 1):
        lines.append(f"{i}. {q}")
    lines.append("")
    return "\n".join(lines)


def generate_project_md(project: Path, output: Path, language: str = "zh", repo: str | None = None, project_type: str | None = None) -> None:
    output.write_text(render_project_md(project, repo=repo, language=language, project_type=project_type), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate PROJECT.md from current project snapshot")
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--language", default="zh", choices=["zh", "en"])
    parser.add_argument("--repo", default=None)
    args = parser.parse_args()
    generate_project_md(args.project.expanduser().resolve(), args.output, language=args.language, repo=args.repo)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
