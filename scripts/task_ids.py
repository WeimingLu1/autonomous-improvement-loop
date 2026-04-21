from __future__ import annotations

from pathlib import Path
import re


def next_task_id(plans_dir: Path) -> str:
    ids: list[int] = []
    for path in plans_dir.glob("TASK-*.md"):
        m = re.match(r"TASK-(\d+)\.md", path.name)
        if m:
            ids.append(int(m.group(1)))
    return f"TASK-{(max(ids) + 1 if ids else 1):03d}"
