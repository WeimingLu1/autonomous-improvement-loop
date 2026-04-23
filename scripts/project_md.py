#!/usr/bin/env python3
from __future__ import annotations

import ast
import argparse
import re
import subprocess
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



def _parse_imports_from_file(p: Path) -> tuple[set[str], set[str]]:
    """
    Parse actual import statements from a Python file using AST.
    Returns (direct_imports, from_imports) where each is a set of module names.
    Uses ast.parse to correctly skip strings, comments, and docstrings.
    """
    direct_imports: set[str] = set()
    from_imports: set[str] = set()

    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return direct_imports, from_imports

    try:
        tree = ast.parse(text, filename=str(p))
    except SyntaxError:
        # Fall back to empty on syntax errors (e.g., partial files)
        return direct_imports, from_imports

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                # Get the root module (first component)
                root = alias.name.split(".")[0]
                direct_imports.add(root)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                root = node.module.split(".")[0]
                from_imports.add(root)

    return direct_imports, from_imports


def _file_uses_git(p: Path) -> bool:
    """Check if a file contains subprocess.run(['git', ...]) pattern."""
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return False
    # Look for subprocess.run(["git", ...) or subprocess.run(['git', ...)
    return bool(re.search(r'subprocess\.run\s*\(\s*\[\s*["\']git["\']', text))


def detect_tech_stack(project: Path, kind: str) -> str:
    """Detect tech stack from real import statements, not string matching."""
    all_files = list(_walk_files(project))
    py_files = [p for p in all_files if p.suffix == ".py"]

    # Collect all imports across all Python files
    all_direct: set[str] = set()
    all_from: set[str] = set()
    git_users: set[Path] = set()

    for p in py_files:
        direct, from_mods = _parse_imports_from_file(p)
        all_direct.update(direct)
        all_from.update(from_mods)
        if _file_uses_git(p):
            git_users.add(p)

    stack: list[str] = []
    if kind == "software":
        if any(p.suffix == ".py" for p in all_files):
            stack.append("Python")

        # Detect based on actual imports
        if "typer" in all_from or "typer" in all_direct:
            stack.append("Typer")
        if "click" in all_from or "click" in all_direct:
            stack.append("Click")
        if "subprocess" in all_from or "subprocess" in all_direct:
            stack.append("Subprocess")
        if "pytest" in all_from or "pytest" in all_direct:
            stack.append("Pytest")
        if "sqlalchemy" in all_from or "sqlalchemy" in all_direct:
            stack.append("SQLAlchemy")
        if "sqlite3" in all_from or "sqlite3" in all_direct:
            stack.append("SQLite")

        # Detect git usage
        if git_users:
            stack.append("Git")

        # Check for Node.js
        if any(p.name == "package.json" for p in all_files):
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
    """Count CLI commands using @app.command (Typer) or @click.command (Click)."""
    count = 0
    for p in _walk_files(project):
        if p.suffix == ".py":
            text = p.read_text(encoding="utf-8", errors="ignore")
            # Match @app.command( and @click.command(
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


def _get_module_inventory(project: Path, lang: str) -> str:
    """Build a module inventory table for software projects."""
    scripts_dir = project / "scripts"
    if not scripts_dir.exists():
        return ""

    module_descriptions: list[tuple[str, str]] = []

    for py_file in sorted(scripts_dir.glob("*.py")):
        if py_file.name.startswith("__"):
            continue
        try:
            text = py_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        # Get docstring from the file
        docstring = ""
        m = re.search(r'"""(.*?)"""', text, re.DOTALL)
        if not m:
            m = re.search(r"'''(.*?)'''", text, re.DOTALL)
        if m:
            docstring = m.group(1).strip().split("\n")[0][:60]

        # If no docstring, try to infer from function names
        if not docstring:
            func_names = re.findall(r"^\s*(?:async\s+)?def\s+(\w+)", text, re.MULTILINE)
            if func_names:
                docstring = f"Functions: {', '.join(func_names[:3])}"

        if not docstring:
            docstring = "—"

        module_descriptions.append((f"`scripts/{py_file.name}`", docstring))

    if not module_descriptions:
        return ""

    if lang == "zh":
        header = "## 核心模块\n\n| 模块 | 说明 |\n|------|------|\n"
    else:
        header = "## Core Modules\n\n| Module | Description |\n|--------|-------------|\n"

    rows = "\n".join(f"| {name} | {desc} |" for name, desc in module_descriptions)
    return header + rows + "\n"


def _get_change_stats(project: Path, lang: str) -> str:
    """Get commit and file change statistics for last 30 days."""
    try:
        # Get commit count in last 30 days
        result = subprocess.run(
            ["git", "log", "--since=30 days ago", "--oneline"],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=10
        )
        commit_count = len(result.stdout.strip().split("\n")) if result.stdout.strip() else 0
    except Exception:
        commit_count = 0

    try:
        # Get files changed in last 30 days
        result = subprocess.run(
            ["git", "diff", "--stat", "--since=30 days ago"],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=10
        )
        # Last line has the summary like "10 files changed, 123 insertions(+)"
        lines = result.stdout.strip().split("\n")
        files_changed = 0
        if lines:
            last_line = lines[-1]
            m = re.search(r"(\d+)\s+file", last_line)
            if m:
                files_changed = int(m.group(1))
    except Exception:
        files_changed = 0

    if lang == "zh":
        return (
            "## 最近动态\n\n"
            f"- 最近 30 天提交：{commit_count} 次\n"
            f"- 最近 30 天文件变更：{files_changed} 个\n"
        )
    else:
        return (
            "## Recent Activity\n\n"
            f"- Commits in last 30 days: {commit_count}\n"
            f"- Files changed in last 30 days: {files_changed}\n"
        )


def render_project_md(project: Path, repo: str | None = None, language: str = "zh", project_type: str | None = None) -> str:
    kind = project_type if project_type is not None else detect_project_type(project)
    repo = repo or detect_repo(project)
    version = detect_version(project)
    stack = detect_tech_stack(project, kind)
    inspires = _get_inspire_questions(kind, language)
    snapshot = summarize_snapshot(project, kind, language)
    caps = core_capabilities(project, kind, language)
    name = project.name

    # Build module inventory and change stats for software projects
    module_inventory = _get_module_inventory(project, language) if kind == "software" else ""
    change_stats = _get_change_stats(project, language) if kind == "software" else ""

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
        ]

        # Add module inventory and change stats
        if module_inventory:
            lines.append(module_inventory)
            lines.append("---")
            lines.append("")
        if change_stats:
            lines.append(change_stats)
            lines.append("---")
            lines.append("")

        lines += [
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
    ]

    # Add module inventory and change stats
    if module_inventory:
        lines.append(module_inventory)
        lines.append("---")
        lines.append("")
    if change_stats:
        lines.append(change_stats)
        lines.append("---")
        lines.append("")

    lines += [
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