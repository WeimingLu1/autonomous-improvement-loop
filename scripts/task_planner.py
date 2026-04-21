from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re


@dataclass
class PlannedTask:
    task_type: str
    source: str
    title: str
    context: str
    why_now: str
    scope: list[str]
    non_goals: list[str]
    relevant_files: list[str]
    execution_plan: list[str]
    acceptance_criteria: list[str]
    verification: list[str]
    risks: list[str]


def _project_summary(project: Path) -> str:
    p = project / "PROJECT.md"
    if not p.exists():
        return f"Project: {project.name}"
    text = p.read_text(encoding="utf-8", errors="ignore")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:400]


def choose_next_task(project: Path, roadmap, done_titles: set[str], language: str) -> PlannedTask:
    summary = _project_summary(project)
    if getattr(roadmap, "next_default_type", "idea") == "idea":
        candidates = [
            "为 a-current 增加完整计划文档回显能力",
            "为 ROADMAP 模型增加当前任务摘要与计划联动输出",
            "为 CLI 增加 roadmap 驱动的任务规划入口",
        ]
        for title in candidates:
            if title not in done_titles:
                return PlannedTask(
                    task_type="idea",
                    source="pm",
                    title=title,
                    context=summary,
                    why_now="当前任务系统正在从一句话队列迁移到 plan 驱动执行，需要先让用户能直接看到完整任务文档。",
                    scope=["生成 current task plan", "回显完整 plan doc", "为后续命令重构打基础"],
                    non_goals=["不实现多任务 backlog", "不重做整个 cron 流程"],
                    relevant_files=["scripts/init.py", "scripts/roadmap.py", "scripts/plan_writer.py"],
                    execution_plan=["读取 ROADMAP current task", "定位 plans/TASK-xxx.md", "把完整文档输出给用户"],
                    acceptance_criteria=["a-current 输出完整 plan 文档", "a-plan 在生成任务后立即输出 plan"],
                    verification=["pytest tests/test_cli_integration.py -q"],
                    risks=["旧命令别名兼容可能受影响"],
                )
    candidates = [
        "为 roadmap 命令流补齐集成测试覆盖",
        "为 current task 和 plan 输出补齐 CLI 测试",
        "为 roadmap 状态迁移增加回归测试",
    ]
    for title in candidates:
        if title not in done_titles:
            return PlannedTask(
                task_type="improve",
                source="pm",
                title=title,
                context=summary,
                why_now="命令流正在重构，优先补齐测试可以降低后续连续迭代的回归风险。",
                scope=["覆盖 a-plan", "覆盖 a-current", "覆盖别名兼容行为"],
                non_goals=["不扩大到所有历史命令"],
                relevant_files=["tests/test_cli_integration.py"],
                execution_plan=["编写 CLI 集成测试", "验证输出内容", "验证 alias 行为"],
                acceptance_criteria=["关键新命令都有 CLI 测试"],
                verification=["pytest tests/test_cli_integration.py -q"],
                risks=["测试依赖 roadmap 初始化"],
            )
    raise ValueError("No unique task title available")
