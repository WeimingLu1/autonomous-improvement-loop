# Autonomous Improvement Loop — Bug Fix Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix all 21 identified bugs (2 Critical, 11 Major, 8 Minor) across 9 Python scripts

**Architecture:** Point fixes per bug with minimal refactoring — each bug fixed in isolation to avoid introducing new issues. No architectural changes.

**Tech Stack:** Python 3, subprocess, re, json, fcntl (for file locking)

---

## Task 1: Fix Critical Bugs (C1, C2) — HEARTBEAT.md schema and run_status choices

**Files:**
- Modify: `autonomous-improvement-loop/scripts/run_status.py:128-135` (choices)
- Modify: `autonomous-improvement-loop/scripts/update_heartbeat.py:174-189` (field writes)
- Modify: `autonomous-improvement-loop/HEARTBEAT.md` (add missing columns)

- [ ] **Step 1: Add "unverified" to run_status.py choices**

File: `autonomous-improvement-loop/scripts/run_status.py` line ~131

Change:
```python
write_parser.add_argument("--result", required=True, choices=["pass", "fail"])
```
To:
```python
write_parser.add_argument("--result", required=True, choices=["pass", "fail", "unverified"])
```

- [ ] **Step 2: Fix write_status to handle None for cron_lock/mode**

File: `autonomous-improvement-loop/scripts/run_status.py` lines ~101-109

Change:
```python
def write_status(
    heartbeat: Path,
    commit: str,
    result: str,
    task: str,
    cron_lock: str = "unchanged",
    mode: str = "unchanged",
):
    ...
    resolved_cron_lock = current_cron_lock if cron_lock == "unchanged" else cron_lock
```
To:
```python
def write_status(
    heartbeat: Path,
    commit: str,
    result: str,
    task: str,
    cron_lock: str | None = None,
    mode: str | None = None,
):
    ...
    current_cron_lock = status.get("cron_lock", "false")
    resolved_cron_lock = current_cron_lock if cron_lock is None else cron_lock
    resolved_mode = status.get("mode", "normal") if mode is None else mode
```

- [ ] **Step 3: Update run_status.py read_status to also read last_run_result and last_run_task**

File: `autonomous-improvement-loop/scripts/run_status.py` lines ~42-51

Add `last_run_result` and `last_run_task` to the extracted status dict.

- [ ] **Step 4: Update HEARTBEAT.md Run Status table to include missing columns**

Add `last_run_result` and `last_run_task` columns to the Run Status table in HEARTBEAT.md. Current Run Status has:
```
| last_run_time | ... |
| last_run_commit | ... |
| cron_lock | ... |
| last_generated_content | ... |
```

Must add:
```
| last_run_result | pass/fail/unverified |
| last_run_task | task description |
```

---

## Task 2: Fix Major Bug M2 — Add file locking to prevent concurrent corruption

**Files:**
- Modify: `autonomous-improvement-loop/scripts/inspire_scanner.py` (add flock)
- Modify: `autonomous-improvement-loop/scripts/update_heartbeat.py` (add flock)
- Modify: `autonomous-improvement-loop/scripts/run_status.py` (add flock)
- Modify: `autonomous-improvement-loop/scripts/verify_and_revert.py` (add flock)

- [ ] **Step 1: Create helper module for file locking**

Create: `autonomous-improvement-loop/scripts/file_lock.py`

```python
"""Atomic file lock helpers using fcntl.flock."""
from contextlib import contextmanager
from pathlib import Path
import fcntl
import time

class FileLock:
    """Exclusive advisory lock on a file."""

    def __init__(self, path: Path, timeout: float = 30.0):
        self.path = path
        self.timeout = timeout
        self._fd = None

    def acquire(self) -> bool:
        self._fd = open(self.path, "a")
        start = time.monotonic()
        while True:
            try:
                fcntl.flock(self._fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                return True
            except BlockingIOError:
                if time.monotonic() - start >= self.timeout:
                    return False
                time.sleep(0.1)

    def release(self):
        if self._fd is not None:
            fcntl.flock(self._fd.fileno(), fcntl.LOCK_UN)
            self._fd.close()
            self._fd = None

    def __enter__(self):
        if not self.acquire():
            raise TimeoutError(f"Could not acquire lock on {self.path}")
        return self

    def __exit__(self, *args):
        self.release()

@contextmanager
def lock_file(path: Path, timeout: float = 30.0):
    """Context manager for file locking."""
    lock = FileLock(path, timeout)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()
```

- [ ] **Step 2: Add locking to update_heartbeat.py**

Wrap HEARTBEAT.md read/write in `lock_file(HEARTBEAT.lock_path)` in:
- `update_heartbeat.py` — before reading heartbeat, before writing heartbeat
- `run_status.py` — in `read_status` and `write_status`
- `inspire_scanner.py` — in `refresh_inspire_queue` and `run_inspire_scan`

---

## Task 3: Fix Major Bug M1 + M6 — Alternation counter drift and desync

**Files:**
- Modify: `autonomous-improvement-loop/scripts/inspire_scanner.py` lines ~985-1035

- [ ] **Step 1: Track consumed alternation slots even when skipped**

In `refresh_inspire_queue`, when a slot's candidates are all duplicates and we skip, we must still advance the alternation correctly. The issue is that `len(generated_rows)` doesn't count skipped slots.

Change the logic so `_advance_alternation_state` is called when we **decide** the type for a slot, not when we successfully add a candidate.

- [ ] **Step 2: Make refresh_inspire_queue the sole entry point for queue rebuild**

`run_inspire_scan` calls `_count_trailing_improves_since_last_idea` and then generates items. `refresh_inspire_queue` does the same. The counter can desync if both are called.

Ensure `refresh_inspire_queue` always uses the current Run Status counter (reads from heartbeat) at start, and updates Run Status with new counter value after generation. Make `run_inspire_scan` call `refresh_inspire_queue` internally rather than having separate logic.

---

## Task 4: Fix Major Bug M4 — JSON regex can't parse nested objects

**Files:**
- Modify: `autonomous-improvement-loop/scripts/priority_scorer.py` lines ~45-55

- [ ] **Step 1: Replace restrictive regex with json.loads fallback**

Change:
```python
json_match = re.search(r"\{[^{}]*\}", raw, re.DOTALL)
```
To:
```python
# Try direct parse first
try:
    return json.loads(raw)
except json.JSONDecodeError:
    # Fallback: find JSON in text using a more permissive pattern
    # Handle nested braces by looking for balanced braces or finding the JSON bounds
    import re
    # Look for JSON-like content starting with { and ending with }
    json_match = re.search(r"\{[\s\S]*\}", raw)
    if json_match:
        try:
            return json.loads(json_match.group())
        except json.JSONDecodeError:
            pass
return {"score": 50, "reason": "Default score (failed to parse evaluation)"}
```

---

## Task 5: Fix Major Bug M7 — Inspire question regex doesn't match markdown headers

**Files:**
- Modify: `autonomous-improvement-loop/scripts/inspire_scanner.py` line ~691

- [ ] **Step 1: Fix regex to match standard markdown headers**

Change:
```python
m = re.search(r"##\s*开放方向[^#]*##", text, re.DOTALL)
```
To:
```python
# Match ## at start, text, optional closing ## or end of line
m = re.search(r"##\s+开放方向[^\n#]*", text, re.MULTILINE)
```

Also fix the English version pattern similarly.

---

## Task 6: Fix Major Bug M5 — Improve items get wrong score from score_finding

**Files:**
- Modify: `autonomous-improvement-loop/scripts/project_insights.py` lines ~449-473

- [ ] **Step 1: In append_to_queue, force score=45 for improve type**

In `append_to_queue` function, when `type_label == "improve"`, use score=45 regardless of `score_finding` result.

---

## Task 7: Fix Major Bugs M8, M9, M10 — verify_and_revert issues

**Files:**
- Modify: `autonomous-improvement-loop/scripts/verify_and_revert.py`

- [ ] **Step 1: Add timeout to verification subprocess (M8)**

Line ~64-65:
```python
return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=300)
```

- [ ] **Step 2: Handle zero-commit repos (M10)**

After `current_head()` check:
```python
head = current_head(cwd=project)
if not head:
    print("ERROR: No commits in project — cannot verify or revert", file=sys.stderr)
    return 1
```

- [ ] **Step 3: Improve revert logic for amended/rebased history (M9)**

Use `git revert -n START..END && git commit` to revert a range of commits rather than assuming single commit hash is still valid.

---

## Task 8: Fix Major Bug M11 — detect_tech_stack() calls _walk_files() 5+ times

**Files:**
- Modify: `autonomous-improvement-loop/scripts/project_md.py` lines ~61-86

- [ ] **Step 1: Cache _walk_files() result in detect_tech_stack()**

Call `_walk_files(project)` once, store in local variable, reuse for all checks. Read file contents once and cache in dict for reuse.

---

## Task 9: Fix Minor Bug m1 — last_generated_content regex doesn't match newlines

**Files:**
- Modify: `autonomous-improvement-loop/scripts/inspire_scanner.py` line ~105

- [ ] **Step 1: Add re.DOTALL flag**

```python
m = re.search(r'\|\s*last_generated_content\s*\|\s*(.+?)\s*\|', text, re.DOTALL)
```

---

## Task 10: Fix Minor Bug m2 — cmd_add doesn't sanitize pipe characters

**Files:**
- Modify: `autonomous-improvement-loop/scripts/init.py` line ~1217

- [ ] **Step 1: Sanitize pipe characters in cmd_add**

In `cmd_add`, before passing to `project_insights.append_to_queue`:
```python
content_text = content_text.replace("|", "/").replace("\n", " ")
```

---

## Task 11: Fix Minor Bug m3 — Done Log insertion places new entry after first row

**Files:**
- Modify: `autonomous-improvement-loop/scripts/update_heartbeat.py` lines ~164-166

- [ ] **Step 1: Fix Done Log insertion to append at end**

Change the regex to find the last data row in Done Log, not just the first. Or insert at end of all `|...|` rows in Done Log section.

```python
# Find the end of Done Log section — after last row
dl_match = re.search(r"(\n## Done Log\n\n\| Time \| Commit \| Task \| Result \|\n)(.*?)(\n## |\Z)", content, re.DOTALL)
if dl_match:
    # Insert after the last row
    insert_pos = dl_match.end(2)
    content = content[:insert_pos] + done_entry + content[insert_pos:]
```

---

## Task 12: Fix Minor Bug m4 — inspire_context parameter is dead code

**Files:**
- Modify: `autonomous-improvement-loop/scripts/inspire_scanner.py` lines ~408-418

- [ ] **Step 1: Use inspire_context in call_llm detail generation**

In `call_llm`, incorporate `inspire_context` into the detail field when available.

---

## Task 13: Fix Minor Bug m5 — heartbeat_path config field is ignored

**Files:**
- Modify: `autonomous-improvement-loop/scripts/update_heartbeat.py` lines ~34-35

- [ ] **Step 1: Make --heartbeat optional, default to config value or default path**

---

## Task 14: Fix Minor Bug m6 — Invalid project_language silently falls back to English

**Files:**
- Modify: `autonomous-improvement-loop/scripts/do_scan.py` line ~69

- [ ] **Step 1: Validate project_language values**

If `project_language` is not `en` or `zh`, warn and fall back to `en`.

---

## Task 15: Fix Minor Bug m7 — detect_project_type() called twice (double tree walk)

**Files:**
- Modify: `autonomous-improvement-loop/scripts/update_heartbeat.py` line ~431

- [ ] **Step 1: Pass project_type from update_heartbeat to render_project_md**

Call `detect_project_type` once in `update_heartbeat`, pass result to `render_project_md` to avoid double call.

---

## Task 16: Fix Minor Bug m8 — Status write failures silently ignored

**Files:**
- Modify: `autonomous-improvement-loop/scripts/verify_and_revert.py` lines ~99-103

- [ ] **Step 1: Check return code and warn on failure**

```python
if r.returncode != 0:
    print(r.stderr, file=sys.stderr)
    return r.returncode  # Don't silently continue
```

---

## Task 17: Test and verify all fixes

**Files:**
- Create: `autonomous-improvement-loop/tests/test_bug_fixes.py`

- [ ] **Step 1: Write comprehensive test for all bug fixes**

Test each fixed behavior:
- `run_status.py` accepts "unverified" result
- `write_status` handles None cron_lock/mode correctly
- File locking prevents concurrent access corruption
- JSON parser handles nested objects
- Inspire question regex matches standard markdown
- `append_to_queue` forces improve=45 score
- Done Log insertion goes at end
- Verify no regressions in existing tests

- [ ] **Step 2: Run all existing tests**

Run: `pytest tests/ -v` to verify no regressions.