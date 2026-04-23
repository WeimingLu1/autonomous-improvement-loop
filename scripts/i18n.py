"""
Internationalization (i18n) messages for the Autonomous Improvement Loop CLI.

All user-facing strings that need to be translated are defined here.
Language is selected at runtime based on --lang argument or project config.
"""

from __future__ import annotations

from typing import Callable


# ── Message dictionaries ──────────────────────────────────────────────────────

MESSAGES: dict[str, dict[str, str]] = {
    "zh": {
        # cmd_status strings
        "checking_project_status": "📊 检查项目状态",
        "project": "项目",
        "path": "路径",
        "github": "GitHub",
        "not_detected": "未检测到（稍后手动配置）",
        "cli_name": "CLI 名称",
        "language": "语言",
        "project_type": "项目类型",
        "agent_id": "Agent ID",
        "readiness_checks": "📋 就绪检查",
        "missing": "（缺失）",
        "project_fully_configured": "项目已完全配置",
        "project_has_missing_items": "项目存在缺失项",
        "current_task": "🧠 当前任务",
        "id": "ID",
        "title": "标题",
        "status": "状态",
        "type": "类型",
        "created": "创建时间",
        "reserved_user_task": "预留用户任务",
        "no_current_task": "ROADMAP.md 中没有当前任务",
        "roadmap_not_found": "未找到 ROADMAP.md — 请先运行 a-plan",
        "cron_job_id": "Cron Job ID",
        "cron_job_not_detected": "Cron Job: 未检测到",
        "all_ok": "✓ 全部检查通过",
        "some_missing": "⚠ 部分检查未通过",

        # Other common messages
        "cancelled": "\n\n已取消。",
        "auto_detected_project": "自动检测到项目: {project}",
        "no_project_found": "错误：无法自动检测项目路径。请在项目目录内运行或手动指定。",
        "specify_project_manually": "\n未在以下位置找到 Git 仓库：\n  ~/Projects/\n  ~/projects/\n  ~/Code/\n\n请手动指定，例如：python init.py a-adopt ~/Projects/YourProject",
        "done": "完成",
        "error": "错误",
        "warning": "警告",
        "info": "信息",
    },
    "en": {
        # cmd_status strings
        "checking_project_status": "📊 Checking project status",
        "project": "Project",
        "path": "Path",
        "github": "GitHub",
        "not_detected": "Not detected (configure manually later)",
        "cli_name": "CLI name",
        "language": "Language",
        "project_type": "Project type",
        "agent_id": "Agent ID",
        "readiness_checks": "📋 Readiness checks",
        "missing": "(missing)",
        "project_fully_configured": "Project is fully configured",
        "project_has_missing_items": "Project has missing readiness items",
        "current_task": "🧠 Current task",
        "id": "ID",
        "title": "Title",
        "status": "Status",
        "type": "Type",
        "created": "Created",
        "reserved_user_task": "Reserved user task",
        "no_current_task": "No current task in ROADMAP.md",
        "roadmap_not_found": "ROADMAP.md not found — run a-plan first",
        "cron_job_id": "Cron Job ID",
        "cron_job_not_detected": "Cron Job: not detected",
        "all_ok": "✓ All checks passed",
        "some_missing": "⚠ Some checks failed",

        # Other common messages
        "cancelled": "\n\nCancelled.",
        "auto_detected_project": "Auto-detected project: {project}",
        "no_project_found": "Error: could not auto-detect a project path. Pass one explicitly or run inside a project directory.",
        "specify_project_manually": "\nNo Git repository was found in:\n  ~/Projects/\n  ~/projects/\n  ~/Code/\n\nSpecify one manually, for example: python init.py a-adopt ~/Projects/YourProject",
        "done": "Done",
        "error": "Error",
        "warning": "Warning",
        "info": "Info",
    },
}

DEFAULT_LANG = "zh"  # Chinese is the project default


def get_message(key: str, lang: str | None = None) -> str:
    """Get a translated message string."""
    if lang is None:
        lang = DEFAULT_LANG
    return MESSAGES.get(lang, MESSAGES[DEFAULT_LANG]).get(
        key, MESSAGES["en"].get(key, key)
    )


def get_lang(lang: str | None = None) -> str:
    """Resolve language to a supported code."""
    if lang and lang in MESSAGES:
        return lang
    return DEFAULT_LANG


# Language display names
LANG_DISPLAY: dict[str, dict[str, str]] = {
    "zh": {"zh": "中文", "en": "中文"},
    "en": {"zh": "Chinese", "en": "English"},
}
