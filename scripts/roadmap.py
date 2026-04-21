from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

CURRENT_TASK_HEADER = "| task_id | type | source | title | status | created |"
DONE_LOG_HEADER = "| time | task_id | type | source | title | result | commit |"


@dataclass
class CurrentTask:
    task_id: str
    task_type: str
    source: str
    title: str
    status: str
    created: str


@dataclass
class RoadmapState:
    current_task: CurrentTask | None
    next_default_type: str
    improves_since_last_idea: int
    current_plan_path: str
    reserved_user_task_id: str


def init_roadmap(path: Path) -> None:
    path.write_text(
        "# Roadmap\n\n"
        "## Current Task\n\n"
        f"{CURRENT_TASK_HEADER}\n"
        "|--------|------|--------|-------|--------|---------|\n\n"
        "## Rhythm State\n\n"
        "| field | value |\n"
        "|------|-------|\n"
        "| next_default_type | idea |\n"
        "| improves_since_last_idea | 0 |\n"
        "| current_plan_path |  |\n"
        "| reserved_user_task_id |  |\n\n"
        "## PM Notes\n\n"
        "- Roadmap initialized.\n\n"
        "## Done Log\n\n"
        f"{DONE_LOG_HEADER}\n"
        "|------|---------|------|--------|-------|--------|--------|\n",
        encoding="utf-8",
    )


def _extract_current_task(text: str) -> CurrentTask | None:
    rows = re.findall(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$", text, re.MULTILINE)
    for row in rows:
        if row[0] in {"task_id", "--------", "field", "------", "time"}:
            continue
        if row[0].startswith("TASK-"):
            return CurrentTask(
                task_id=row[0].strip(),
                task_type=row[1].strip(),
                source=row[2].strip(),
                title=row[3].strip(),
                status=row[4].strip(),
                created=row[5].strip(),
            )
    return None


def _get_rhythm_value(text: str, field: str, default: str = "") -> str:
    m = re.search(rf"\|\s*{re.escape(field)}\s*\|\s*([^|]*)\|", text)
    return m.group(1).strip() if m else default


def _extract_done_log_block(text: str) -> str:
    match = re.search(r"## Done Log\n\n([\s\S]*)\Z", text)
    if match:
        block = match.group(1).strip("\n")
        if block:
            return block + "\n"
    return DONE_LOG_HEADER + "\n|------|---------|------|--------|-------|--------|--------|\n"


def _render_roadmap(task: CurrentTask | None, *, next_default_type: str, improves_since_last_idea: int, plan_path: str, reserved_user_task_id: str, done_log_block: str) -> str:
    current_row = ""
    if task is not None:
        current_row = f"| {task.task_id} | {task.task_type} | {task.source} | {task.title} | {task.status} | {task.created} |\n"
    return (
        "# Roadmap\n\n"
        "## Current Task\n\n"
        f"{CURRENT_TASK_HEADER}\n"
        "|--------|------|--------|-------|--------|---------|\n"
        f"{current_row}\n"
        "## Rhythm State\n\n"
        "| field | value |\n"
        "|------|-------|\n"
        f"| next_default_type | {next_default_type} |\n"
        f"| improves_since_last_idea | {improves_since_last_idea} |\n"
        f"| current_plan_path | {plan_path} |\n"
        f"| reserved_user_task_id | {reserved_user_task_id} |\n\n"
        "## PM Notes\n\n"
        "- Roadmap initialized.\n\n"
        "## Done Log\n\n"
        f"{done_log_block.rstrip()}\n"
    )


def load_roadmap(path: Path) -> RoadmapState:
    text = path.read_text(encoding="utf-8")
    return RoadmapState(
        current_task=_extract_current_task(text),
        next_default_type=_get_rhythm_value(text, "next_default_type", "idea") or "idea",
        improves_since_last_idea=int(_get_rhythm_value(text, "improves_since_last_idea", "0") or "0"),
        current_plan_path=_get_rhythm_value(text, "current_plan_path", ""),
        reserved_user_task_id=_get_rhythm_value(text, "reserved_user_task_id", ""),
    )


def set_current_task(path: Path, task: CurrentTask | None, plan_path: str, next_default_type: str, improves_since_last_idea: int, reserved_user_task_id: str = "") -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    done_log_block = _extract_done_log_block(text)
    path.write_text(
        _render_roadmap(
            task,
            next_default_type=next_default_type,
            improves_since_last_idea=improves_since_last_idea,
            plan_path=plan_path,
            reserved_user_task_id=reserved_user_task_id,
            done_log_block=done_log_block,
        ),
        encoding="utf-8",
    )


def append_done_log(path: Path, *, timestamp: str, task_id: str, task_type: str, source: str, title: str, result: str, commit: str) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    row = f"| {timestamp} | {task_id} | {task_type} | {source} | {title} | {result} | {commit} |\n"
    done_log_block = _extract_done_log_block(text)
    if row not in done_log_block:
        done_log_block += row
    state = load_roadmap(path) if path.exists() else RoadmapState(None, "idea", 0, "", "")
    path.write_text(
        _render_roadmap(
            state.current_task,
            next_default_type=state.next_default_type,
            improves_since_last_idea=state.improves_since_last_idea,
            plan_path=state.current_plan_path,
            reserved_user_task_id=state.reserved_user_task_id,
            done_log_block=done_log_block,
        ),
        encoding="utf-8",
    )
