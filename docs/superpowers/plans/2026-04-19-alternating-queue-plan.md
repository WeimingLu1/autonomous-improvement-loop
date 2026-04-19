# Alternating Queue — Implementation Plan

> **Spec:** `docs/superpowers/specs/2026-04-19-alternating-queue-design.md`
> **Skill:** autonomous-improvement-loop

---

## Phase 1: Alternation Framework

### Task 1: Add alternation state helpers to inspire_scanner

**Files:**
- Modify: `scripts/inspire_scanner.py`

**Steps:**

- [ ] **Step 1: Add `_get_last_done_type()` — read Done Log for last task type**

```python
def _get_last_done_type(heartbeat: Path) -> str | None:
    """
    Read the most recent Done Log entry and return its task type.
    Returns 'idea', 'improve', or None if no entries exist.
    """
    if not heartbeat.exists():
        return None
    text = heartbeat.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"## Done Log\b[\s\S]*?\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^\|]+?)\s*\|", text)
    # Find the LAST data row (not header, not separator)
    rows = re.findall(r"\|\s*(\d{4}-\d{2}-\d{2}[^\|]*?)\s*\|\s*`?([a-f0-9]+)`?\s*\|\s*([^\|]+?)\s*\|", text)
    if not rows:
        return None
    last_task = rows[-1][2].strip()
    if "[[Idea]]" in last_task:
        return "idea"
    if "[[Improve]]" in last_task:
        return "improve"
    return None
```

- [ ] **Step 2: Add `_get_improves_since_idea()` — read Run Status counter**

```python
def _get_improves_since_idea(heartbeat: Path) -> int:
    """Read improves_since_last_idea counter from Run Status."""
    if not heartbeat.exists():
        return 0
    text = heartbeat.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"\|\s*improves_since_last_idea\s*\|\s*(\d+)\s*\|", text)
    return int(m.group(1)) if m else 0
```

- [ ] **Step 3: Add `_set_improves_since_idea()` — write Run Status counter**

```python
def _set_improves_since_idea(heartbeat: Path, count: int) -> None:
    """
    Update or insert the improves_since_last_idea row in Run Status.
    Removes legacy 'inspire_scan_cycle' field if present.
    """
    if not heartbeat.exists():
        return
    text = heartbeat.read_text(encoding="utf-8", errors="ignore")

    # Remove legacy inspire_scan_cycle HTML comment
    text = re.sub(r"<!--\s*inspire_scan_cycle:\s*\d+\s*-->\s*", "", text)
    # Remove legacy inspire_scan_cycle plain row
    text = re.sub(r"\n?\|?\s*inspire_scan_cycle\s*\|\s*\d+\s*\|?\s*\n?", "\n", text)

    counter_row = f"| improves_since_last_idea | {count} |"
    if re.search(r"\|\s*improves_since_last_idea\s*\|\s*\d+\s*\|", text):
        text = re.sub(
            r"(\|\s*improves_since_last_idea\s*\|\s*)\d+(\s*\|)",
            rf"\g<1>{count}\g<2>",
            text,
            count=1,
        )
    elif "## Run Status" in text:
        # Insert as first row after the header separator
        m = re.search(r"(\|[^|]+\|[^|]+\|\n\|?---+?\|?---+\|?\n)", text)
        if m:
            text = text[:m.end()] + counter_row + "\n" + text[m.end():]
    heartbeat.write_text(text, encoding="utf-8")
```

- [ ] **Step 4: Add `_decide_next_type()` — alternation decision logic**

```python
def _decide_next_type(heartbeat: Path) -> str:
    """
    Decide whether to generate 'idea' or 'improve' on this cycle.
    Rules:
      - No Done Log entries → 'idea'
      - Last was 'idea'   → 'improve'
      - Last was 'improve' → if counter >= 2: 'idea' (reset counter); else 'improve' (counter + 1)
    """
    last_type = _get_last_done_type(heartbeat)
    counter = _get_improves_since_idea(heartbeat)

    if last_type is None:
        # First run ever
        return "idea"
    if last_type == "idea":
        _set_improves_since_idea(heartbeat, 0)
        return "improve"
    if last_type == "improve":
        if counter >= 2:
            _set_improves_since_idea(heartbeat, 0)
            return "idea"
        else:
            _set_improves_since_idea(heartbeat, counter + 1)
            return "improve"
    return "idea"  # fallback
```

- [ ] **Step 5: Commit**

```bash
git add scripts/inspire_scanner.py
git commit -m "feat(inspire): add alternation state helpers"
```

---

## Phase 2: Improve Generators

### Task 2: Write Improve generators per project kind

**Files:**
- Modify: `scripts/inspire_scanner.py`

**Steps:**

- [ ] **Step 1: Add `_get_recent_git_activity()` — parse git log for active modules**

```python
def _get_recent_git_activity(project: Path, n: int = 20) -> list[tuple[str, int]]:
    """
    Run 'git log --oneline -n --stat' and return list of (module_path, lines_changed).
    module_path is the top-level src/ subdirectory or module name.
    Returns empty list if not a git repo or git fails.
    """
    import subprocess
    result = subprocess.run(
        ["git", "log", f"--oneline", f"-{n}", "--stat", "--", "*.py"],
        cwd=str(project),
        capture_output=True,
        text=True,
        timeout=10,
    )
    if result.returncode != 0:
        return []
    # Parse stat: count '+' and '-' lines per file
    module_scores: dict[str, int] = {}
    current_file = None
    for line in result.stdout.splitlines():
        m = re.match(r"\s*(\d+)\s+(?:insertions?\+|deletions?\+|-)\s+(.+)$", line.strip()):
            if m:
                lines, fname = int(m.group(1)), m.group(2).strip()
                if fname.endswith(".py") and "/" in fname:
                    parts = fname.split("/")
                    # src/services/module.py → services/module
                    if "src" in parts:
                        idx = parts.index("src")
                        module = "/".join(parts[idx+1:])
                    else:
                        module = "/".join(parts)
                    module_scores[module] = module_scores.get(module, 0) + lines
    return sorted(module_scores.items(), key=lambda x: -x[1])
```

- [ ] **Step 2: Add `_software_improve_generator()` — Git-based Improve for software**

```python
def _software_improve_generator(project: Path, language: str, seen: set[str]) -> list[tuple[str, str, int]]:
    """
    Generate 1 Improve task based on most-active module in recent Git commits.
    Returns list of (content, detail, score=45).
    """
    activity = _get_recent_git_activity(project, n=20)
    if not activity:
        # Fallback: generic
        content = "审视项目，找出最近最需要改进的模块并优先实施改进"
        return [(content, content, 45)]

    top_module, _ = activity[0]  # most changed module

    # Map module to Improve template
    templates_zh = {
        "services/":    "基于最近 Git 提交分析，{module} 是高频改动模块。"
                         "建议：补充该模块所有公开函数的边界测试（None/空列表/异常输入），"
                         "并验证 recent {module} 公开 API 的合约是否完整",
        "cli/":         "cli/{module} 最近改动较多，建议审查并补充错误处理和边界测试，"
                         "确保 --help 和 --json 两种输出模式均有测试覆盖",
        "rules/":       "rules/{module} 规则引擎最近有改动，建议补充该规则的"
                         "全部边界情况测试（窗口边界、None 字段、极端值）",
        "parsers/":     "parsers/{module} 最近有更新，建议补充解析器的"
                         "边界测试（空输入、畸形输入、特殊字符、超长输入）",
    }
    templates_en = {
        "services/":    "Recent commits show {module} is the most-active module. "
                         "Add targeted unit tests covering boundary conditions "
                         "(None inputs, empty lists, exception paths) for all "
                         "public functions in that module.",
        "cli/":         "{module} has recent changes. Add CLI boundary tests "
                         "covering --help, --json, and error output modes.",
        "rules/":        "rules/{module} has recent rule changes. Add boundary "
                         "tests for window edges, None fields, and extreme values.",
        "parsers/":     "parsers/{module} recently updated. Add parser boundary "
                         "tests: empty input, malformed input, special chars, "
                         "over-length input.",
    }

    templates = templates_zh if language == "zh" else templates_en
    content_template = None
    for prefix, tpl in templates.items():
        if top_module.startswith(prefix):
            content_template = tpl
            break
    if content_template is None:
        content_template = templates_zh.get("", templates_en.get("", "审视项目，找出最需要改进的地方并优先实施")) if language == "zh" else "Review the most-active module ({module}) for targeted improvements."

    module_name = top_module.rsplit("/", 1)[-1] if "/" in top_module else top_module
    content = content_template.format(module=top_module, module_name=module_name)

    # Truncate at 200 chars
    if len(content) > 200:
        content = content[:197] + "..."

    norm = _normalize_text(content)
    if norm in seen:
        return []
    return [(content, content, 45)]
```

- [ ] **Step 3: Add writing/video/research/generic Improve generators**

```python
def _writing_improve_generator(project: Path, language: str, seen: set[str]) -> list[tuple[str, str, int]]:
    """Find the oldest or smallest chapter and suggest improving it."""
    chapters_dir = project / "chapters"
    if not chapters_dir.exists():
        return [("审视写作项目结构和内容完整性，找出最需要改进的章节并优先实施" if language == "zh" else
                 "Review writing project structure and improve the weakest chapter.", "", 45)]
    chapters = sorted(chapters_dir.glob("*.md"), key=lambda p: p.stat().st_mtime)
    if not chapters:
        return [("审视写作项目结构和内容完整性，找出最需要改进的章节并优先实施" if language == "zh" else
                 "Review writing project structure and improve the weakest chapter.", "", 45)]
    oldest = chapters[0]
    content = (f"章节 {oldest.stem} 是项目中最久未更新的章节。"
               f"建议审查其内容完整性、论证逻辑和与最新章节的衔接，并进行修订。"
               if language == "zh" else
               f"Chapter {oldest.stem} is the least recently updated. Review its content completeness, argument structure, and coherence with recent chapters.")
    return [(content, content, 45)] if _normalize_text(content) not in seen else []


def _video_improve_generator(project: Path, language: str, seen: set[str]) -> list[tuple[str, str, int]]:
    """Find the制作状态最落后的 scene and suggest improving it."""
    scenes_dir = project / "scenes"
    if not scenes_dir.exists():
        return [("审视视频制作项目，找出制作进度最落后的场景并优先完善" if language == "zh" else
                 "Review video production project and improve the most incomplete scene.", "", 45)]
    scenes = sorted(scenes_dir.iterdir(), key=lambda p: p.stat().st_mtime)
    if not scenes:
        return [("审视视频制作项目，找出制作进度最落后的场景并优先完善" if language == "zh" else
                 "Review video production project and improve the most incomplete scene.", "", 45)]
    oldest = scenes[0]
    content = (f"场景 {oldest.stem} 是项目中最久未更新的素材。"
               f"建议审查其脚本完整度、画面质量和与整体叙事的衔接，并进行修订。"
               if language == "zh" else
               f"Scene {oldest.stem} is the least recently updated. Review its script completeness, visual quality, and narrative alignment.")
    return [(content, content, 45)] if _normalize_text(content) not in seen else []


def _research_improve_generator(project: Path, language: str, seen: set[str]) -> list[tuple[str, str, int]]:
    """Suggest reviewing the weakest argument chain or updating references."""
    refs_dir = project / "references"
    notes_dir = project / "notes"
    content = ("研究项目中可能存在论证链条不够严谨的章节。"
                "建议全面审查论文假设、证据链完整性和引用准确性，补充必要的参考文献。"
                if language == "zh" else
                "Review the research project for weak argument chains. Check hypothesis validity, evidence completeness, and citation accuracy. Add missing references.")
    return [(content, content, 45)] if _normalize_text(content) not in seen else []


def _generic_improve_generator(project: Path, language: str, seen: set[str]) -> list[tuple[str, str, int]]:
    """Generic fallback: find the most impactful improvement area."""
    content = ("审视项目，找出用户抱怨最多或最影响工作效率的一个具体问题，优先修复"
               if language == "zh" else
               "Identify the issue most impacting user experience or developer productivity and fix it.")
    return [(content, content, 45)] if _normalize_text(content) not in seen else []
```

- [ ] **Step 4: Commit**

```bash
git add scripts/inspire_scanner.py
git commit -m "feat(inspire): add Improve generators per project kind"
```

---

## Phase 3: Restructure Idea + run_inspire_scan

### Task 3: Clean up Idea generators, remove every_n

**Files:**
- Modify: `scripts/inspire_scanner.py`

**Steps:**

- [ ] **Step 1: Remove old cycle helpers** — delete `_get_inspire_cycle`, `_set_inspire_cycle`, `_pending_idea_count`, and the old HTML-comment cycle injection logic. Keep `_detect_existing_queue_content` and `_normalize_text`.

- [ ] **Step 2: Add dispatch table for Improve generators**

```python
IMPROVE_GENERATORS: dict[str, callable] = {
    "software":  _software_improve_generator,
    "writing":   _writing_improve_generator,
    "video":     _video_improve_generator,
    "research":  _research_improve_generator,
    "generic":   _generic_improve_generator,
}
```

- [ ] **Step 3: Rewrite `run_inspire_scan()`**

```python
def run_inspire_scan(
    project: Path,
    heartbeat: Path | None = None,
    *,
    language: str = "zh",
) -> dict:
    """
    Alternating queue manager.

    1. Decide next type (idea or improve) via alternation rules
    2. Generate content using appropriate per-kind generator
    3. Write to HEARTBEAT queue (replace all same-type items)
    4. Return result dict

    Returns:
        {
            "generated": "idea" | "improve",
            "content": str,
            "score": int,
            "detail": str,
            "source": str,
            "improves_since_last_idea": int,  # current counter after this run
        }
    """
    heartbeat = heartbeat or HEARTBEAT
    project_md = project / "PROJECT.md"
    if not project_md.exists():
        project_md = SKILL_DIR / "PROJECT.md"

    # ── 1. Decide type ────────────────────────────────────────────────────
    next_type = _decide_next_type(heartbeat)

    # ── 2. Read existing queue for deduplication ──────────────────────────
    seen = _detect_existing_queue_content(heartbeat)

    # ── 3. Generate content ──────────────────────────────────────────────
    kind = _detect_project_type(project)
    kind = kind if kind in IMPROVE_GENERATORS else "software"

    candidates: list[tuple[str, str, int]] = []  # (content, detail, score)

    if next_type == "idea":
        # Use per-kind idea generators (existing SOFTWARE_IDEA_GENERATORS_ZH/EN etc.)
        candidates = _generate_software_ideas(project, language, seen)  # reuse existing
        if not candidates and kind == "generic":
            candidates = _generate_generic_ideas(language, seen)
    else:
        gen_fn = IMPROVE_GENERATORS.get(kind, IMPROVE_GENERATORS["generic"])
        candidates = gen_fn(project, language, seen)

    if not candidates:
        return {
            "generated": next_type,
            "content": "(no candidate generated)",
            "score": 0,
            "detail": "",
            "source": "",
            "improves_since_last_idea": _get_improves_since_idea(heartbeat),
        }

    # Pick best candidate (highest score, deduplicated)
    candidates.sort(key=lambda x: -x[2])
    content, detail, score = candidates[0]

    source = (
        f"inspire: {_load_inspire_questions(project_md, language)[0]}"
        if next_type == "idea" else
        f"git: {_get_recent_git_activity(project)[0][0] if _get_recent_git_activity(project) else 'project'}"
    )

    # ── 4. Write to HEARTBEAT queue ──────────────────────────────────────
    rows = _read_queue_rows(heartbeat)
    # Remove old items of the same type
    rows = [r for r in rows if r.get("type", "").strip().lower() != next_type]
    # Add new item
    rows.append({
        "type": next_type,
        "score": str(score),
        "content": f"[[{next_type.capitalize()}]] {content}",
        "detail": detail,
        "source": source,
        "status": "pending",
        "created": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
    })
    # Sort: pending first, then by score desc
    rows.sort(key=lambda r: (0 if r.get("status", "").lower() == "pending" else 1, -int(r.get("score", "0") or 0)))
    _write_queue_rows(heartbeat, rows)

    return {
        "generated": next_type,
        "content": content,
        "score": score,
        "detail": detail,
        "source": source,
        "improves_since_last_idea": _get_improves_since_idea(heartbeat),
    }
```

- [ ] **Step 4: Update `update_heartbeat.py` step 5 call**

```python
# Replace the old inspire_scanner call block with:
try:
    from inspire_scanner import run_inspire_scan
    result = run_inspire_scan(project=project, heartbeat=heartbeat_p, language=language)
    print(f"Queue ({result['generated']}): {result['content'][:60]}")
    print(f"Improves since last idea: {result['improves_since_last_idea']}")
except Exception as e:
    print(f"WARNING: inspire scan failed: {e}", file=sys.stderr)
```

- [ ] **Step 5: Update `init.py` cron message section 4**

Find line:
```python
        4. Execute the highest-priority pending queue item — both [[Improve]] (maintenance/tasks) and [[Idea]] (functional improvements) are valid choices. Prefer [[Idea]] items when they have a score ≥ 40.
```

Replace with:
```python
        4. Execute the current pending queue item. The item type alternates:
           after a [[Improve]], the next cycle produces a [[Idea]], and vice versa.
           There is always exactly one pending item — simply execute it.
```

- [ ] **Step 6: Update inspire_scanner CLI (remove --every-n)**

```python
# Remove --every-n from argparse; update docstring
# Remove every_n parameter from run_inspire_scan signature
```

- [ ] **Step 7: Commit**

```bash
git add scripts/inspire_scanner.py scripts/update_heartbeat.py scripts/init.py
git commit -m "feat(inspire): rewrite run_inspire_scan with alternation logic"
```

---

## Phase 4: Tests

### Task 4: Write unit tests

**Files:**
- Create: `tests/test_inspire_scanner.py`

**Steps:**

- [ ] **Step 1: Create test file with fixtures**

```python
import pytest, subprocess, tempfile
from pathlib import Path
from inspire_scanner import (
    _get_last_done_type, _get_improves_since_idea, _set_improves_since_idea,
    _decide_next_type, run_inspire_scan,
)

MINIMAL_HB = """## Queue

| # | Type | Score | Content | Detail | Source | Status | Created |
|---|------|-------|---------|--------|--------|--------|--------|

---

## Run Status

| Field | Value |
|-------|-------|
| improves_since_last_idea | 0 |

---

## Done Log

| Time | Commit | Task | Result |
|------|--------|------|--------|
"""
```

- [ ] **Step 2: Alternation tests**

```python
def test_first_run_generates_idea(tmp_path):
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text(MINIMAL_HB, encoding="utf-8")
    # No Done Log → should decide 'idea'
    result = run_inspire_scan(project=tmp_path, heartbeat=hb, language="zh")
    assert result["generated"] == "idea"


def test_idea_then_improve(tmp_path):
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text(
        MINIMAL_HB
        + "| 2026-04-19T10:00:00Z | abc123 | [[Idea]] 测试 Idea | test | inspire | pass |\n",
        encoding="utf-8",
    )
    result = run_inspire_scan(project=tmp_path, heartbeat=hb, language="zh")
    assert result["generated"] == "improve"
    assert _get_improves_since_idea(hb) == 1


def test_improve_x2_then_idea(tmp_path):
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text(
        MINIMAL_HB
        + "| 2026-04-19T10:00:00Z | abc123 | [[Improve]] 测试 Improve | test | scanner | pass |\n",
        encoding="utf-8",
    )
    # First Improve (counter was 0, becomes 1)
    r1 = run_inspire_scan(project=tmp_path, heartbeat=hb, language="zh")
    assert r1["generated"] == "improve"
    assert _get_improves_since_idea(hb) == 1

    # Second Improve (counter is 1, becomes 2 → triggers Idea)
    hb.write_text(hb.read_text() + "| 2026-04-19T11:00:00Z | def456 | [[Improve]] 测试 Improve 2 | test | scanner | pass |\n", encoding="utf-8")
    r2 = run_inspire_scan(project=tmp_path, heartbeat=hb, language="zh")
    assert r2["generated"] == "idea"
    assert _get_improves_since_idea(hb) == 0


def test_idea_resets_counter(tmp_path):
    hb = tmp_path / "HEARTBEAT.md"
    # Set counter to 2 (about to trigger Idea)
    content = MINIMAL_HB.replace("| improves_since_last_idea | 0 |", "| improves_since_last_idea | 2 |")
    hb.write_text(content, encoding="utf-8")
    result = run_inspire_scan(project=tmp_path, heartbeat=hb, language="zh")
    assert result["generated"] == "idea"
    assert _get_improves_since_idea(hb) == 0


def test_queue_replaced_not_appended(tmp_path):
    """Running twice should replace, not add."""
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text(MINIMAL_HB, encoding="utf-8")
    run_inspire_scan(project=tmp_path, heartbeat=hb, language="zh")
    from inspire_scanner import _read_queue_rows
    rows_after_first = _read_queue_rows(hb)
    run_inspire_scan(project=tmp_path, heartbeat=hb, language="zh")
    rows_after_second = _read_queue_rows(hb)
    # Should still be 1 item, not 2
    assert len(rows_after_first) == 1
    assert len(rows_after_second) == 1
```

- [ ] **Step 3: Run tests**

```bash
cd /Users/weiminglu/.openclaw/workspace-viya/skills/autonomous-improvement-loop
python -m pytest tests/test_inspire_scanner.py -v
```

- [ ] **Step 4: Commit**

```bash
git add tests/test_inspire_scanner.py
git commit -m "test: add inspire_scanner unit tests"
```

---

## Phase 5: Integration Test

### Task 5: End-to-end verification

**Steps:**

- [ ] **Step 1: Run inspire_scanner on the real HealthAgent HEARTBEAT**

```bash
cd /Users/weiminglu/.openclaw/workspace-viya/skills/autonomous-improvement-loop
# First save a backup
cp HEARTBEAT.md HEARTBEAT.md.backup

python -c "
import sys
sys.path.insert(0, 'scripts')
from pathlib import Path
from inspire_scanner import run_inspire_scan
result = run_inspire_scan(
    project=Path('/Users/weiminglu/Projects/HealthAgent'),
    heartbeat=Path('HEARTBEAT.md'),
    language='zh',
)
print('Generated:', result['generated'])
print('Content:', result['content'][:80])
print('Score:', result['score'])
print('Counter:', result['improves_since_last_idea'])
"
```

- [ ] **Step 2: Verify queue has exactly 1 item**

```bash
python scripts/init.py a-queue
```

Expected: 1 item, type alternating correctly.

- [ ] **Step 3: Restore HEARTBEAT from backup**

```bash
cp HEARTBEAT.md.backup HEARTBEAT.md
```

- [ ] **Step 4: Commit all remaining changes**

```bash
git add -A && git commit -m "feat: complete alternating queue implementation"
```

---

## Verification Checklist

After all tasks complete, run:

```bash
# 1. Compilation check
python -m py_compile scripts/inspire_scanner.py
python -m py_compile scripts/update_heartbeat.py
python -m py_compile scripts/init.py

# 2. Unit tests
python -m pytest tests/test_inspire_scanner.py -v

# 3. Queue display
python scripts/init.py a-queue

# 4. Verify alternation (run 3 times, check types)
# Run 1: idea (first run), Run 2: improve (counter=1), Run 3: improve (counter=2→idea)
```
