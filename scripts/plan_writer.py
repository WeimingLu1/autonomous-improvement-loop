from __future__ import annotations

from pathlib import Path


def _bullets(items: list[str]) -> str:
    return "\n".join(f"- {item}" for item in items) if items else "- None"


def write_plan_doc(
    plans_dir: Path,
    task_id: str,
    title: str,
    task_type: str = "idea",
    source: str = "pm",
    context: str = "",
    why_now: str = "",
    scope: list[str] | None = None,
    non_goals: list[str] | None = None,
    relevant_files: list[str] | None = None,
    execution_plan: list[str] | None = None,
    acceptance_criteria: list[str] | None = None,
    verification: list[str] | None = None,
    risks: list[str] | None = None,
) -> Path:
    plans_dir.mkdir(parents=True, exist_ok=True)
    plan_path = (plans_dir / f"{task_id}.md").resolve()
    content = f"# {task_id} · {title}\n\n"
    content += f"- Type: {task_type}\n- Source: {source}\n\n"
    content += f"## Goal\n{title}\n\n"
    content += f"## Context\n{context or 'N/A'}\n\n"
    content += f"## Why now\n{why_now or 'N/A'}\n\n"
    content += f"## Scope\n{_bullets(scope or [])}\n\n"
    content += f"## Non-goals\n{_bullets(non_goals or [])}\n\n"
    content += f"## Relevant Files\n{_bullets(relevant_files or [])}\n\n"
    content += f"## Execution Plan\n{_bullets(execution_plan or [])}\n\n"
    content += f"## Acceptance Criteria\n{_bullets(acceptance_criteria or [])}\n\n"
    content += f"## Verification\n{_bullets(verification or [])}\n\n"
    content += f"## Risks / Notes\n{_bullets(risks or [])}\n"
    plan_path.write_text(content, encoding="utf-8")
    return plan_path
