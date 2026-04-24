from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

CURRENT_TASK_HEADER = "| task_id | type | source | title | priority | status | created |"
DONE_LOG_HEADER = "| time | task_id | type | source | title | result | commit |"


@dataclass
class CurrentTask:
    task_id: str
    task_type: str
    source: str
    title: str
    priority: str = 'P1'
    status: str = 'pending'
    created: str = ''


@dataclass
class RoadmapState:
    current_task: CurrentTask | None
    next_default_type: str
    improves_since_last_idea: int
    post_feature_maintenance_remaining: int = 0  # 0=normal, 1 or 2=maintenance slots left
    maintenance_anchor_title: str = ""
    current_plan_path: str = ""
    reserved_user_task_id: str = ""
    maintenance_mode: bool = False


def init_roadmap(path: Path) -> None:
    path.write_text(
        "# Roadmap\n\n"
        "## Current Task\n\n"
        f"{CURRENT_TASK_HEADER}\n"
        "|--------|------|--------|-------|----------|--------|---------|\n\n"
        "## Rhythm State\n\n"
        "| field | value |\n"
        "|------|-------|\n"
        "| next_default_type | idea |\n"
        "| improves_since_last_idea | 0 |\n"
        "| post_feature_maintenance_remaining | 0 |\n"
        "| maintenance_anchor_title |  |\n"
        "| current_plan_path |  |\n"
        "| reserved_user_task_id |  |\n"
        "| maintenance_mode | false |\n\n"
        "## PM Notes\n\n"
        "- Roadmap initialized.\n\n"
        "## Done Log\n\n"
        f"{DONE_LOG_HEADER}\n"
        "|------|---------|------|--------|-------|--------|--------|\n",
        encoding="utf-8",
    )


def _extract_current_task(text: str) -> CurrentTask | None:
    section_match = re.search(r"## Current Task\n\n([\s\S]*?)\n## ", text)
    section = section_match.group(1) if section_match else text
    rows = re.findall(r"^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|$", section, re.MULTILINE)
    for row in rows:
        if row[0] in {"task_id", "--------", "field", "------", "time"}:
            continue
        if row[0].startswith("TASK-"):
            return CurrentTask(
                task_id=row[0].strip(),
                task_type=row[1].strip(),
                source=row[2].strip(),
                title=row[3].strip(),
                priority=row[4].strip() or 'P1',
                status=row[5].strip(),
                created=row[6].strip(),
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


def _render_roadmap(task: CurrentTask | None, *, next_default_type: str, improves_since_last_idea: int, post_feature_maintenance_remaining: int, maintenance_anchor_title: str, plan_path: str, reserved_user_task_id: str, maintenance_mode: bool, done_log_block: str) -> str:
    current_row = ""
    if task is not None:
        current_row = f"| {task.task_id} | {task.task_type} | {task.source} | {task.title} | {task.priority} | {task.status} | {task.created} |\n"
    return (
        "# Roadmap\n\n"
        "## Current Task\n\n"
        f"{CURRENT_TASK_HEADER}\n"
        "|--------|------|--------|-------|----------|--------|---------|\n"
        f"{current_row}\n"
        "## Rhythm State\n\n"
        "| field | value |\n"
        "|------|-------|\n"
        f"| next_default_type | {next_default_type} |\n"
        f"| improves_since_last_idea | {improves_since_last_idea} |\n"
        f"| post_feature_maintenance_remaining | {post_feature_maintenance_remaining} |\n"
        f"| maintenance_anchor_title | {maintenance_anchor_title} |\n"
        f"| current_plan_path | {plan_path} |\n"
        f"| reserved_user_task_id | {reserved_user_task_id} |\n"
        f"| maintenance_mode | {'true' if maintenance_mode else 'false'} |\n\n"
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
        post_feature_maintenance_remaining=int(_get_rhythm_value(text, "post_feature_maintenance_remaining", "0") or "0"),
        maintenance_anchor_title=_get_rhythm_value(text, "maintenance_anchor_title", ""),
        current_plan_path=_get_rhythm_value(text, "current_plan_path", ""),
        reserved_user_task_id=_get_rhythm_value(text, "reserved_user_task_id", ""),
        maintenance_mode=_get_rhythm_value(text, "maintenance_mode", "false") in ("true", "1", "yes"),
    )


def normalize_roadmap(path: Path) -> RoadmapState:
    """Normalize inconsistent roadmap state in place.

    - Clear Current Task when it is already marked done/pass.
    - Clear stale maintenance anchor when no maintenance slots remain.
    """
    state = load_roadmap(path)
    dirty = False

    current_task = state.current_task
    if current_task and current_task.status.strip().lower() in {"done", "pass"}:
        current_task = None
        dirty = True

    maintenance_anchor_title = state.maintenance_anchor_title
    if state.post_feature_maintenance_remaining <= 0 and maintenance_anchor_title:
        maintenance_anchor_title = ""
        dirty = True

    if dirty:
        set_current_task(
            path,
            current_task,
            plan_path="" if current_task is None else state.current_plan_path,
            next_default_type=state.next_default_type,
            improves_since_last_idea=state.improves_since_last_idea,
            post_feature_maintenance_remaining=max(0, state.post_feature_maintenance_remaining),
            maintenance_anchor_title=maintenance_anchor_title,
            reserved_user_task_id=state.reserved_user_task_id,
            maintenance_mode=state.maintenance_mode,
        )
        return load_roadmap(path)

    return state


def set_current_task(path: Path, task: CurrentTask | None, plan_path: str, next_default_type: str, improves_since_last_idea: int, post_feature_maintenance_remaining: int = 0, maintenance_anchor_title: str = "", reserved_user_task_id: str = "", maintenance_mode: bool = False) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    done_log_block = _extract_done_log_block(text)
    path.write_text(
        _render_roadmap(
            task,
            next_default_type=next_default_type,
            improves_since_last_idea=improves_since_last_idea,
            post_feature_maintenance_remaining=post_feature_maintenance_remaining,
            maintenance_anchor_title=maintenance_anchor_title,
            plan_path=plan_path,
            reserved_user_task_id=reserved_user_task_id,
            maintenance_mode=maintenance_mode,
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
    state = load_roadmap(path) if path.exists() else RoadmapState(None, "idea", 0, 0, "", "", "", False)
    path.write_text(
        _render_roadmap(
            state.current_task,
            next_default_type=state.next_default_type,
            improves_since_last_idea=state.improves_since_last_idea,
            post_feature_maintenance_remaining=state.post_feature_maintenance_remaining,
            maintenance_anchor_title=state.maintenance_anchor_title,
            plan_path=state.current_plan_path,
            reserved_user_task_id=state.reserved_user_task_id,
            maintenance_mode=state.maintenance_mode,
            done_log_block=done_log_block,
        ),
        encoding="utf-8",
    )
