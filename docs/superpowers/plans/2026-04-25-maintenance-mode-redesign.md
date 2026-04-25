# Maintenance Mode 任务去重重新实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 maintenance mode 的去重从 title 字符串匹配改为 maintenance_tag 版本计数，支持同一 tag 的任务多次出现（v2/v3），并实现内容差异化。

**Architecture:**
- Done Log schema 新增 `tag` 列，兼容旧格式（无 tag 列视为空）
- `task_planner.py` 新增 `_maintenance_tag_versions()` 解析 Done Log，按 tag 分组计数
- 候选生成时，tag 有记录则标题加 vN，scope 从 git diff 动态注入
- `maintenance_mode=True` 时跳过 `improves_since_last_idea` 计数
- post-feature maintenance 那套 anchor_title + remaining 逻辑保持不变

**Tech Stack:** Python 3, argparse, pathlib, re, subprocess (git)

---

## 文件变更概览

| 文件 | 变更类型 | 职责 |
|------|---------|------|
| `scripts/roadmap.py` | Modify | Done Log schema 新增 tag 列；`append_done_log` 支持 `tag` 参数 |
| `scripts/task_planner.py` | Modify | `_maintenance_tag_versions()`；tag 版本标题生成；内容差异化 |
| `scripts/cli.py` | Modify | `cmd_status` / `cmd_maintenance` 输出 maintenance_mode 状态 |
| `scripts/init.py` | Modify | 透传 `maintenance_tag` 到 `append_done_log` |
| `scripts/_maintenance.py` | Create | 从 `task_planner.py` 提取 maintenance 相关候选生成逻辑（可选重构，先内嵌） |
| `tests/test_maintenance_mode.py` | Create | maintenance mode 专项测试 |

---

## 实现任务

### Task 1: Done Log Schema 变更 — 新增 tag 列

**Files:**
- Modify: `scripts/roadmap.py:8` (DONE_LOG_HEADER)
- Modify: `scripts/roadmap.py:189-208` (append_done_log)
- Modify: `scripts/roadmap.py:93` (_render_roadmap done_log_block)

- [ ] **Step 1: 更新 DONE_LOG_HEADER**

当前：
```python
DONE_LOG_HEADER = "| time | task_id | type | source | title | result | commit |"
```

改为：
```python
DONE_LOG_HEADER = "| time | task_id | type | source | tag | title | result | commit |"
```

同时更新 `_extract_done_log_block` 的默认值 separator：
```python
return DONE_LOG_HEADER + "\n|------|---------|------|--------|----|-------|--------|--------|\n"
```

- [ ] **Step 2: 修改 append_done_log 支持 tag 参数**

签名变更：
```python
def append_done_log(path: Path, *, timestamp: str, task_id: str, task_type: str, source: str, tag: str, title: str, result: str, commit: str) -> None:
```

行写入：
```python
row = f"| {timestamp} | {task_id} | {task_type} | {source} | {tag} | {title} | {result} | {commit} |\n"
```

- [ ] **Step 3: 兼容旧格式（无 tag 列的 Done Log）**

`_extract_done_log_block` 保持兼容：旧格式没有第 5 列 `tag`，解析时用 `tag = ""` 填充。

在 `load_roadmap` 或单独新增 `_parse_done_log_entries(text)` 函数返回带 tag 的 dict list：
```python
def _parse_done_log_entries(block: str) -> list[dict]:
    """Parse Done Log block into list of dicts with tag field (empty string if absent)."""
    entries = []
    for line in block.splitlines():
        if line.startswith("|") and "time" not in line:
            parts = [p.strip() for p in line.strip().strip("|").split("|")]
            # Support both old (7 cols) and new (8 cols) formats
            if len(parts) == 7:
                parts.insert(4, "")  # insert empty tag at position 4
            elif len(parts) == 8:
                pass  # already has tag
            else:
                continue
            entries.append({
                "time": parts[0],
                "task_id": parts[1],
                "task_type": parts[2],
                "source": parts[3],
                "tag": parts[4],
                "title": parts[5],
                "result": parts[6],
                "commit": parts[7],
            })
    return entries
```

- [ ] **Step 4: 更新 _render_roadmap 的 done_log_block 处理**

确认 `_render_roadmap` 透传的 `done_log_block` 不受影响（因为它只承接已经格式化好的 block string，不关心内部列结构）。不需要改。

- [ ] **Step 5: 验证**

```bash
cd /Users/weiminglu/Projects/autonomous-improvement-loop
python3 -c "
from scripts.roadmap import append_done_log, _parse_done_log_entries, _extract_done_log_block
from pathlib import Path
import tempfile, time

# Test: append with tag, then parse
tmp = Path(tempfile.mktemp(suffix='.md'))
from scripts.roadmap import _render_roadmap, RoadmapState

state = RoadmapState(None, 'idea', 0, 0, '', '', '', False)
init_content = _render_roadmap(None, next_default_type='idea', improves_since_last_idea=0, post_feature_maintenance_remaining=0, maintenance_anchor_title='', plan_path='', reserved_user_task_id='', maintenance_mode=False, done_log_block='| time | task_id | type | source | tag | title | result | commit |\n')
tmp.write_text(init_content)

append_done_log(tmp, timestamp='2026-04-25T00:00:00Z', task_id='TASK-999', task_type='maintenance', source='pm', tag='security', title='进行安全漏洞审计', result='pass', commit='abc123')
block = _extract_done_log_block(tmp.read_text())
entries = _parse_done_log_entries(block)
assert len(entries) == 1
assert entries[0]['tag'] == 'security', f'got {entries[0][\"tag\"]}'
print('OK: tag column works, parse returns tag correctly')
"
```

Expected: `OK: tag column works, parse returns tag correctly`

- [ ] **Step 6: Commit**

```bash
git add scripts/roadmap.py
git commit -m "feat(roadmap): add tag column to Done Log schema"
```

---

### Task 2: tag 版本计数 + 标题生成

**Files:**
- Modify: `scripts/task_planner.py` — 新增 `_maintenance_tag_versions()` 和 `_maintenance_candidate_title()`

- [ ] **Step 1: 新增 `_maintenance_tag_versions()` 函数**

在 `task_planner.py` 中靠 `_sticky_done_titles()` 附近添加：

```python
def _maintenance_tag_versions(done_log_entries: list[dict]) -> dict[str, int]:
    """Parse Done Log entries and return {tag: version_count} mapping.
    
    version = number of times this tag has appeared in Done Log.
    So if 'security' appears 2 times, the next security task gets v3.
    """
    counts: dict[str, int] = {}
    for entry in done_log_entries:
        tag = entry.get("tag", "")
        if tag:
            counts[tag] = counts.get(tag, 0) + 1
    return counts  # {'security': 2, 'testing': 1}
```

- [ ] **Step 2: 新增 `_maintenance_candidate_title()` 函数**

```python
def _maintenance_candidate_title(candidate: dict, version: int) -> str:
    """Generate maintenance task title with version suffix.
    
    version=1 → original title (no suffix)
    version>=2 → title + " v{version}"
    e.g. "进行安全漏洞审计" → "进行安全漏洞审计 v2"
    """
    if version <= 1:
        return candidate["title"]
    return f"{candidate['title']} v{version}"
```

- [ ] **Step 3: 修改 `_make_task` 支持 maintenance title 版本化**

找到 `_make_task` 的调用位置，特别是 `choose_next_task` 中 `primary_pool = [_make_task("maintenance", c, ctx) for c in _MAINTENANCE_CANDIDATES]` 这里。

修改策略：在 `choose_next_task` 中，生成 maintenance pool 后，对每个候选应用版本标题：

```python
# In choose_next_task, after maintenance_mode branch:
if maintenance_mode:
    # Get tag versions from Done Log
    done_entries = _parse_done_log_entries(_extract_done_log_block(...))  # need to add this import/call
    tag_versions = _maintenance_tag_versions(done_entries)
    
    # Build maintenance pool with versioned titles
    maintenance_pool = []
    for c in _MAINTENANCE_CANDIDATES:
        tag = c.get("maintenance_tag", "")
        version = tag_versions.get(tag, 0) + 1  # next version number
        task = _make_task("maintenance", c, ctx)
        task.title = _maintenance_candidate_title(c, version)  # apply versioned title
        maintenance_pool.append(task)
    
    primary_pool = maintenance_pool
    fallback_pool = improve_pool
```

注意：需要在 `choose_next_task` 中导入 `_parse_done_log_entries` 和 `_extract_done_log_block`，这两个函数在 `roadmap.py` 中。需要确认 `task_planner.py` 已经 import 了 `roadmap` 相关函数。

先确认导入关系：
```bash
grep -n "^from scripts.roadmap\|^from .roadmap" /Users/weiminglu/Projects/autonomous-improvement-loop/scripts/task_planner.py
```

如果 `task_planner.py` 还没有从 `roadmap` 导入这些函数，需要添加：
```python
from scripts.roadmap import _extract_done_log_block, _parse_done_log_entries
```

- [ ] **Step 4: 验证**

```bash
cd /Users/weiminglu/Projects/autonomous-improvement-loop
python3 -c "
from scripts.task_planner import _maintenance_tag_versions, _maintenance_candidate_title

# Test version counting
entries = [
    {'tag': 'security', 'title': '进行安全漏洞审计'},
    {'tag': 'testing', 'title': '补充单元测试覆盖'},
    {'tag': 'security', 'title': '进行安全漏洞审计 v2'},
]
versions = _maintenance_tag_versions(entries)
assert versions == {'security': 2, 'testing': 1}, f'got {versions}'
print(f'security next version: {versions[\"security\"] + 1}')  # should be 3

# Test title generation
candidate = {'title': '进行安全漏洞审计'}
assert _maintenance_candidate_title(candidate, 1) == '进行安全漏洞审计'
assert _maintenance_candidate_title(candidate, 2) == '进行安全漏洞审计 v2'
assert _maintenance_candidate_title(candidate, 3) == '进行安全漏洞审计 v3'
print('OK: tag version and title generation work correctly')
"
```

Expected: `OK: tag version and title generation work correctly`

- [ ] **Step 5: Commit**

```bash
git add scripts/task_planner.py
git commit -m "feat(maintenance): add tag version counting and versioned titles"
```

---

### Task 3: 内容差异化 — scope 从 git diff 动态生成

**Files:**
- Modify: `scripts/task_planner.py` — 扩展 `_read_project_context` 返回变更文件列表；修改候选 scope 动态注入

- [ ] **Step 1: 确认 `_read_project_context` 返回变更文件**

当前 `_read_project_context` 已经返回了 `commits`（最近 10 个 git log）。需要确认它也记录了变更文件。

检查是否有 `git diff --stat` 相关逻辑：
```bash
grep -n "git diff\|git_status\|changed_files" /Users/weiminglu/Projects/autonomous-improvement-loop/scripts/task_planner.py
```

如果没有，新增 `_changed_files_from_git()` 函数：
```python
def _changed_files_from_git(project: Path, since_days: int = 7) -> list[str]:
    """Return list of files changed in last N days via git diff --name-only."""
    try:
        since = f"--since='{since_days} days ago'"
        result = subprocess.run(
            ["git", "diff", "--name-only", since, "--", "."],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode == 0:
            return [f.strip() for f in result.stdout.strip().split("\n") if f.strip()]
    except Exception:
        pass
    return []
```

在 `_read_project_context` 的 return dict 中追加：
```python
return {
    # ... existing fields ...
    "changed_files": _changed_files_from_git(project),
}
```

- [ ] **Step 2: 修改 scope 注入逻辑**

在 `choose_next_task` 的 maintenance pool 生成中，基于 `changed_files` 为每个候选动态构造 scope：

```python
changed_files = ctx.get("changed_files", [])

def _dynamic_scope(candidate: dict, changed_files: list[str]) -> list[str]:
    """Generate dynamic scope based on changed files and maintenance_tag."""
    tag = candidate.get("maintenance_tag", "")
    if not changed_files:
        return candidate.get("scope", ["scripts/"])
    
    # Filter to relevant changed files based on tag
    if tag == "security":
        # Focus on scripts/ and tests/ that were changed
        relevant = [f for f in changed_files if f.startswith(("scripts/", "tests/"))]
    elif tag == "testing":
        relevant = [f for f in changed_files if "test" in f or f.startswith("tests/")]
    elif tag == "docs":
        relevant = [f for f in changed_files if f.endswith(".md") or "docs" in f]
    elif tag == "performance":
        relevant = [f for f in changed_files if f.startswith("scripts/")]
    else:
        relevant = changed_files[:5]  # fallback: first 5 changed files
    
    return relevant[:5] if relevant else candidate.get("scope", ["scripts/"])
```

在 `choose_next_task` 生成 maintenance pool 时，对每个候选注入动态 scope：
```python
task = _make_task("maintenance", c, ctx)
task.scope = _dynamic_scope(c, changed_files)
```

注意：`_make_task` 返回的是 PlannedTask dataclass，需要确认它的 scope 字段可写。检查 PlannedTask 定义：
```bash
grep -n "class PlannedTask\|scope:" /Users/weiminglu/Projects/autonomous-improvement-loop/scripts/task_planner.py | head -20
```

PlannedTask 是 dataclass，`scope: list[str]` 是字段，可以直接赋值。

- [ ] **Step 3: 验证**

```bash
cd /Users/weiminglu/Projects/autonomous-improvement-loop
python3 -c "
from scripts.task_planner import _read_project_context
from pathlib import Path

ctx = _read_project_context(Path('.'))
changed = ctx.get('changed_files', [])
print(f'Changed files in last 7 days: {len(changed)}')
print('First 5:', changed[:5])
"
```

Expected: 显示实际变更文件列表（可能为空）

- [ ] **Step 4: Commit**

```bash
git add scripts/task_planner.py
git commit -m "feat(maintenance): inject dynamic scope from git diff into maintenance candidates"
```

---

### Task 4: post-feature maintenance tag 映射 + Rhythm 调整

**Files:**
- Modify: `scripts/task_planner.py` — `_build_maintenance_candidates` 增加 tag；maintenance_mode 时跳过 `improves_since_last_idea` 计数

- [ ] **Step 1: 为 `_build_maintenance_candidates` 的动态任务增加 tag**

当前 `_build_maintenance_candidates` 返回的 dict 没有 `maintenance_tag` 字段。为两个动态任务补充：

```python
regression = {
    "title": f"回归验证并修复：{anchor}",
    "maintenance_tag": "regression",  # ADD THIS
    # ... rest unchanged
}
docs = {
    "title": f"补测试与文档：{anchor}",
    "maintenance_tag": "testing",  # ADD THIS (aligns with testing tag)
    # ... rest unchanged
}
```

- [ ] **Step 2: maintenance_mode=True 时跳过 improves_since_last_idea 计数**

在 `choose_next_task` 的 maintenance_mode 分支中，设置一个 flag 告知调用方不要增加 `improves_since_last_idea`：

```python
consumed = maintenance_mode  # True means don't count as "improvement"
```

在调用处（`choose_next_task` 返回的 consumed flag），检查逻辑是否使用了这个 flag：

当前 `consumed` 在 `choose_next_task` 返回时是 `maintenance_remaining > 0`。需要确认调用方如何使用 consumed，并确保 `maintenance_mode=True` 时也设置正确的 consumed 值。

实际上，当 `maintenance_mode=True` 时，`post_feature_maintenance_remaining=0`，所以 `consumed = maintenance_remaining > 0` 会是 False。这意味着 maintenance mode 下任务完成后不会被标记为「消耗」，不会触发 rhythm 变化。

但我们需要确保 `maintenance_mode=True` 时，`improves_since_last_idea` 不增加。看当前代码中哪里增加了这个计数器：

```bash
grep -n "improves_since_last_idea" /Users/weiminglu/Projects/autonomous-improvement-loop/scripts/cli.py | head -20
```

找到在 `cmd_trigger` 或 `_generate_next_task` 中增加计数的地方。当任务完成并写入 Done Log 时，需要检查 maintenance_mode 并跳过计数增加。

具体修改位置：在 `scripts/cli.py` 的 `cmd_trigger` 中，任务完成后更新 rhythm 状态时：

```python
# When consuming a maintenance task, don't increment improves_since_last_idea
if consumed and not maintenance_mode:
    new_improves = state.improves_since_last_idea + 1
elif consumed and maintenance_mode:
    new_improves = state.improves_since_last_idea  # skip counting in maintenance mode
else:
    new_improves = 0 if not consumed else state.improves_since_last_idea
```

需要先确认 `cmd_trigger` 中哪段逻辑负责更新 `improves_since_last_idea`。

- [ ] **Step 3: 验证**

启动 maintenance mode，跑几个任务，确认 `improves_since_last_idea` 不增加：
```bash
cd /Users/weiminglu/Projects/autonomous-improvement-loop
python3 -c "
from scripts.roadmap import load_roadmap, set_current_task
from pathlib import Path

roadmap_path = Path('.ail/ROADMAP.md')
state = load_roadmap(roadmap_path)
print(f'Before: maintenance_mode={state.maintenance_mode}, improves={state.improves_since_last_idea}')
"
```

- [ ] **Step 4: Commit**

```bash
git add scripts/task_planner.py scripts/cli.py
git commit -m "feat(maintenance): add regression/testing tags to post-feature tasks; skip rhythm counter in maintenance mode"
```

---

### Task 5: 测试 — maintenance mode 专项测试

**Files:**
- Create: `tests/test_maintenance_mode.py`

- [ ] **Step 1: 写测试文件**

```python
"""Tests for maintenance mode tag-based deduplication."""

import tempfile
import shutil
from pathlib import Path

import pytest

from scripts.roadmap import (
    init_roadmap,
    load_roadmap,
    set_current_task,
    append_done_log,
    _parse_done_log_entries,
    _extract_done_log_block,
    RoadmapState,
)
from scripts.task_planner import (
    _maintenance_tag_versions,
    _maintenance_candidate_title,
    choose_next_task,
)


class TestMaintenanceTagVersions:
    def test_empty_log_returns_empty_dict(self):
        entries = []
        result = _maintenance_tag_versions(entries)
        assert result == {}

    def test_single_tag_counts_correctly(self):
        entries = [{"tag": "security", "title": "审计1"}]
        result = _maintenance_tag_versions(entries)
        assert result == {"security": 1}

    def test_multiple_tags_counted_separately(self):
        entries = [
            {"tag": "security", "title": "审计1"},
            {"tag": "testing", "title": "测试1"},
            {"tag": "security", "title": "审计2"},
        ]
        result = _maintenance_tag_versions(entries)
        assert result == {"security": 2, "testing": 1}

    def test_empty_tag_ignored(self):
        entries = [
            {"tag": "", "title": "some idea"},
            {"tag": "security", "title": "审计1"},
        ]
        result = _maintenance_tag_versions(entries)
        assert result == {"security": 1}


class TestMaintenanceCandidateTitle:
    def test_version_1_returns_original(self):
        candidate = {"title": "进行安全漏洞审计"}
        assert _maintenance_candidate_title(candidate, 1) == "进行安全漏洞审计"

    def test_version_2_adds_v2_suffix(self):
        candidate = {"title": "进行安全漏洞审计"}
        assert _maintenance_candidate_title(candidate, 2) == "进行安全漏洞审计 v2"

    def test_version_3_adds_v3_suffix(self):
        candidate = {"title": "补充单元测试覆盖"}
        assert _maintenance_candidate_title(candidate, 3) == "补充单元测试覆盖 v3"


class TestDoneLogTagSchema:
    def test_append_with_tag_and_parse_roundtrip(self):
        """append_done_log with tag, then _parse_done_log_entries, returns correct tag."""
        tmp = Path(tempfile.mktemp(suffix=".md"))
        shutil.copy(
            Path("tests/fixtures/empty_roadmap.md"),
            tmp,
        )
        append_done_log(
            tmp,
            timestamp="2026-04-25T00:00:00Z",
            task_id="TASK-TEST",
            task_type="maintenance",
            source="pm",
            tag="security",
            title="进行安全漏洞审计",
            result="pass",
            commit="abc123",
        )
        block = _extract_done_log_block(tmp.read_text())
        entries = _parse_done_log_entries(block)
        assert len(entries) == 1
        assert entries[0]["tag"] == "security"
        assert entries[0]["title"] == "进行安全漏洞审计"
        tmp.unlink()

    def test_old_format_without_tag_still_parses(self):
        """Legacy Done Log rows without tag column parse with empty tag."""
        old_block = "| time | task_id | type | source | title | result | commit |\n| 2026-04-24 | TASK-001 | idea | pm | Some task | pass | abc123 |\n"
        entries = _parse_done_log_entries(old_block)
        assert len(entries) == 1
        assert entries[0]["tag"] == ""  # empty tag for legacy format
        assert entries[0]["title"] == "Some task"


class TestMaintenanceModeFreeRotation:
    def test_all_15_candidates_can_be_selected_without_sticky(self, tmp_path):
        """All 15 maintenance candidates can appear in sequence, no title-based sticky."""
        init_roadmap(tmp_path / "ROADMAP.md")
        # Seed with maintenance mode on
        state = load_roadmap(tmp_path / "ROADMAP.md")
        set_current_task(
            tmp_path / "ROADMAP.md",
            state.current_task,
            plan_path=state.current_plan_path,
            next_default_type="idea",
            improves_since_last_idea=0,
            post_feature_maintenance_remaining=0,
            maintenance_anchor_title="",
            reserved_user_task_id="",
            maintenance_mode=True,  # ON
        )
        # Simulate: all 15 candidates appear once each, none blocked
        from scripts.task_planner import _MAINTENANCE_CANDIDATES
        selected = []
        blocked = set()
        for candidate in _MAINTENANCE_CANDIDATES:
            tag = candidate.get("maintenance_tag", "")
            title = candidate["title"]
            # Simulate done_titles behavior: maintenance uses tag-based blocking, not title
            if title in blocked:
                pytest.fail(f"{title} incorrectly blocked after first appearance")
            selected.append((tag, title))
            blocked.add(title)
        assert len(selected) == 15
        assert len(set(tag for tag, _ in selected)) > 1  # multiple tags used
```

创建 `tests/fixtures/empty_roadmap.md` fixture：
```python
# tests/fixtures/empty_roadmap.md
# Just the minimal structure needed
```

- [ ] **Step 2: 运行测试验证**

```bash
cd /Users/weiminglu/Projects/autonomous-improvement-loop
python3 -m pytest tests/test_maintenance_mode.py -v
```

Expected: All tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/test_maintenance_mode.py tests/fixtures/
git commit -m "test(maintenance): add专项 tests for tag-based deduplication"
```

---

## 验证计划

完成所有 Task 后，运行完整测试套件：

```bash
cd /Users/weiminglu/Projects/autonomous-improvement-loop
python3 -m pytest tests/ -q
```

Expected: All tests pass

然后手动验证 maintenance mode 自由轮转：

```bash
cd /Users/weiminglu/Projects/autonomous-improvement-loop
python3 scripts/init.py a-maintenance on
# 查看 maintenance_mode 是否开启
python3 scripts/init.py a-status
# 触发 a-plan 3次，确认每次生成 maintenance 任务且标题带版本号
python3 scripts/init.py a-plan
python3 scripts/init.py a-trigger --no-spawn
python3 scripts/init.py a-current  # 查看任务标题
```

---

## 实施顺序

1. Task 1 (Done Log schema) — 基础，依赖最少
2. Task 2 (tag 版本计数) — 依赖 Task 1
3. Task 3 (内容差异化) — 可独立验证
4. Task 4 (post-feature tag + rhythm) — 依赖 Task 2
5. Task 5 (测试) — 所有阶段完成后做集成验证