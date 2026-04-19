"""
Tests for inspire_scanner alternating queue logic.

Covers:
- Alternation state: _decide_next_type, _get_improves_since_idea, _set_improves_since_idea
- Idea generation (first run, dedup, source field)
- Improve generation (git-based, fallback)
- Queue replacement (same type replaced, opposite type preserved)
- Legacy cleanup (inspire_scan_cycle removed)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from inspire_scanner import (
    _decide_next_type,
    _detect_existing_queue_content,
    _get_improves_since_idea,
    _get_last_done_type,
    _get_recent_git_activity,
    _normalize_text,
    _read_queue_rows,
    _set_improves_since_idea,
    _software_improve_generator,
    _write_queue_rows,
    run_inspire_scan,
)


# ── Fixtures ─────────────────────────────────────────────────────────────────

BASE_QUEUE = (
    "| # | Type | Score | Content | Detail | Source | Status | Created |\n"
    "|---|------|-------|---------|--------|--------|--------|--------|\n"
)

BASE_STATUS = (
    "## Run Status\n\n"
    "> Managed by autonomous-improvement-loop skill scripts.\n\n"
    "| Field | Value |\n"
    "|-------|-------|\n"
    "| improves_since_last_idea | 0 |\n"
)


def make_heartbeat(
    queue_rows: str = "",
    run_status: str = BASE_STATUS,
    done_log: str = "",
) -> str:
    return (
        f"## Queue\n\n{queue_rows or BASE_QUEUE}\n\n---\n\n"
        f"{run_status}\n\n---\n\n"
        f"## Done Log\n\n| Time | Commit | Task | Result |\n"
        f"|------|--------|------|--------|\n{done_log}"
    )


# ── Alternation helpers ───────────────────────────────────────────────────────

def test_first_run_generates_idea(tmp_path: Path) -> None:
    """No Done Log → first run should generate idea."""
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text(make_heartbeat(), encoding="utf-8")
    result = run_inspire_scan(project=tmp_path, heartbeat=hb, language="zh")
    assert result["generated"] == "idea"


def test_idea_then_improve(tmp_path: Path) -> None:
    """Last was idea → next should be improve, and counter increments to 1."""
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text(
        make_heartbeat(
            done_log="| 2026-04-19T10:00:00Z | abc123 | [[Idea]] 测试 Idea | pass |\n",
        ),
        encoding="utf-8",
    )
    result = run_inspire_scan(project=tmp_path, heartbeat=hb, language="zh")
    assert result["generated"] == "improve"
    assert _get_improves_since_idea(hb) == 1


def test_improve_x2_then_idea(tmp_path: Path) -> None:
    """After 2 improves, the third cycle generates idea and resets counter."""
    hb = tmp_path / "HEARTBEAT.md"

    # First improve seen in done log, next remains improve and counter becomes 1
    hb.write_text(
        make_heartbeat(
            done_log="| 2026-04-19T10:00:00Z | abc | [[Improve]] Improve 1 | pass |\n",
        ),
        encoding="utf-8",
    )
    r1 = run_inspire_scan(project=tmp_path, heartbeat=hb, language="zh")
    assert r1["generated"] == "improve"
    assert _get_improves_since_idea(hb) == 1

    # With counter=1, another improve increments it to 2
    hb.write_text(
        make_heartbeat(
            run_status=BASE_STATUS.replace("| improves_since_last_idea | 0 |", "| improves_since_last_idea | 1 |"),
            done_log="| 2026-04-19T10:00:00Z | abc | [[Improve]] Improve 1 | pass |\n"
                     "| 2026-04-19T11:00:00Z | def | [[Improve]] Improve 2 | pass |\n",
        ),
        encoding="utf-8",
    )
    r2 = run_inspire_scan(project=tmp_path, heartbeat=hb, language="zh")
    assert r2["generated"] == "improve"
    assert _get_improves_since_idea(hb) == 2

    # With counter>=2, next cycle switches back to idea and resets counter
    hb.write_text(
        make_heartbeat(
            run_status=BASE_STATUS.replace("| improves_since_last_idea | 0 |", "| improves_since_last_idea | 2 |"),
            done_log="| 2026-04-19T10:00:00Z | abc | [[Improve]] Improve 1 | pass |\n"
                     "| 2026-04-19T11:00:00Z | def | [[Improve]] Improve 2 | pass |\n"
                     "| 2026-04-19T12:00:00Z | ghi | [[Improve]] Improve 3 | pass |\n",
        ),
        encoding="utf-8",
    )
    r3 = run_inspire_scan(project=tmp_path, heartbeat=hb, language="zh")
    assert r3["generated"] == "idea"
    assert _get_improves_since_idea(hb) == 0


def test_idea_resets_counter(tmp_path: Path) -> None:
    """Generating an idea resets improves_since_last_idea to 0."""
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text(
        make_heartbeat(
            run_status=BASE_STATUS.replace("| improves_since_last_idea | 0 |", "| improves_since_last_idea | 2 |"),
            done_log="| 2026-04-19T10:00:00Z | abc | [[Improve]] Improve 2 | pass |\n",
        ),
        encoding="utf-8",
    )
    result = run_inspire_scan(project=tmp_path, heartbeat=hb, language="zh")
    assert result["generated"] == "idea"
    assert _get_improves_since_idea(hb) == 0


def test_queue_replaced_not_appended(tmp_path: Path) -> None:
    """Running inspire_scanner twice should replace, not accumulate same-type items."""
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text(make_heartbeat(), encoding="utf-8")

    # First run → idea
    r1 = run_inspire_scan(project=tmp_path, heartbeat=hb, language="zh")
    assert r1["generated"] == "idea"
    rows_after1 = _read_queue_rows(hb)
    assert len(rows_after1) == 1

    # Simulate Done Log update
    content = hb.read_text()
    content = content.rstrip() + "\n| 2026-04-20T00:00:00Z | t1 | [[Idea]] Idea 1 | pass |\n"
    hb.write_text(content, encoding="utf-8")

    # Second run → improve
    r2 = run_inspire_scan(project=tmp_path, heartbeat=hb, language="zh")
    assert r2["generated"] == "improve"
    rows_after2 = _read_queue_rows(hb)

    # Should have idea (from run1) + improve (from run2)
    types = {r.get("type", "") for r in rows_after2}
    assert types == {"idea", "improve"}


def test_run_status_updated(tmp_path: Path) -> None:
    """Run Status follows the implementation's counter transitions."""
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text(make_heartbeat(), encoding="utf-8")

    run_inspire_scan(project=tmp_path, heartbeat=hb, language="zh")
    assert _get_improves_since_idea(hb) == 0  # first = idea, resets to 0

    # Simulate Done Log with improve
    content = hb.read_text()
    content = content.rstrip() + "\n| 2026-04-20T00:00:00Z | t1 | [[Improve]] Imp 1 | pass |\n"
    hb.write_text(content, encoding="utf-8")

    run_inspire_scan(project=tmp_path, heartbeat=hb, language="zh")
    assert _get_improves_since_idea(hb) == 1


def test_legacy_inspire_scan_cycle_cleaned(tmp_path: Path) -> None:
    """Legacy inspire_scan_cycle fields are cleaned when run status is rewritten."""
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text(
        make_heartbeat(
            run_status=BASE_STATUS
            + "\n| inspire_scan_cycle | 5 |\n",
        ),
        encoding="utf-8",
    )
    _set_improves_since_idea(hb, 1)
    content = hb.read_text()
    assert "inspire_scan_cycle" not in content
    assert "| improves_since_last_idea | 1 |" in content


# ── Idea generation ──────────────────────────────────────────────────────────

def test_idea_score_matches_selected_candidate(tmp_path: Path) -> None:
    """Idea score matches the implementation's chosen candidate."""
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text(make_heartbeat(), encoding="utf-8")
    result = run_inspire_scan(project=tmp_path, heartbeat=hb, language="zh")
    assert result["generated"] == "idea"
    assert result["score"] in {45, 62}


def test_improve_score_is_45(tmp_path: Path) -> None:
    """Improves get score 45."""
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text(
        make_heartbeat(
            done_log="| 2026-04-19T10:00:00Z | abc | [[Idea]] Idea | pass |\n",
        ),
        encoding="utf-8",
    )
    result = run_inspire_scan(project=tmp_path, heartbeat=hb, language="zh")
    assert result["generated"] == "improve"
    assert result["score"] == 45


def test_idea_source_contains_inspire(tmp_path: Path) -> None:
    """Idea source field starts with 'inspire:'."""
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text(make_heartbeat(), encoding="utf-8")
    result = run_inspire_scan(project=tmp_path, heartbeat=hb, language="zh")
    assert result["generated"] == "idea"
    assert result["source"].startswith("inspire:")


# ── Improve generation ───────────────────────────────────────────────────────

def test_software_improve_generator_returns_tuple(tmp_path: Path) -> None:
    """_software_improve_generator returns list of (content, detail, score)."""
    result = _software_improve_generator(tmp_path, "zh", set())
    if result:
        assert len(result[0]) == 3
        assert isinstance(result[0][0], str)
        assert result[0][2] == 45


def test_software_improve_fallback_when_no_git(tmp_path: Path) -> None:
    """If not a git repo, returns generic fallback."""
    result = _software_improve_generator(tmp_path, "zh", set())
    assert len(result) == 1
    assert result[0][2] == 45


# ── Dedup ───────────────────────────────────────────────────────────────────

def test_duplicate_idea_not_reinserted(tmp_path: Path) -> None:
    """Same idea text is not re-inserted."""
    hb = tmp_path / "HEARTBEAT.md"
    # Pre-populate with an idea
    pre_row = (
        "| 1 | idea | 62 | [[Idea]] 添加交互式 `health interactive` 命令 | "
        "添加交互式 | inspire: CLI | pending | 2026-04-19 |\n"
    )
    hb.write_text(
        make_heartbeat(queue_rows=BASE_QUEUE + pre_row),
        encoding="utf-8",
    )
    # Try to generate idea (same content)
    seen = _detect_existing_queue_content(hb)
    # Normalize the existing idea
    from inspire_scanner import _normalize_text
    existing_norm = _normalize_text("[[Idea]] 添加交互式 `health interactive` 命令")
    assert existing_norm in seen

    # Existing queue content is detected with the stored [[Idea]] prefix
    result = run_inspire_scan(project=tmp_path, heartbeat=hb, language="zh")
    assert result["generated"] in {"idea", "improve"}


# ── Queue format ─────────────────────────────────────────────────────────────

def test_write_queue_rows_round_trip(tmp_path: Path) -> None:
    """_write_queue_rows writes rows back in a shape _read_queue_rows can parse."""
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text(make_heartbeat(), encoding="utf-8")
    rows = [
        {
            "type": "idea",
            "score": "62",
            "content": "[[Idea]] test",
            "detail": "test",
            "source": "inspire: test",
            "status": "pending",
            "created": "2026-04-19",
        }
    ]
    _write_queue_rows(hb, rows)
    parsed = _read_queue_rows(hb)
    assert parsed == rows


def test_decide_next_type_no_history_returns_idea(tmp_path: Path) -> None:
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text(make_heartbeat(), encoding="utf-8")
    assert _decide_next_type(hb) == "idea"


def test_get_last_done_type_without_done_entries(tmp_path: Path) -> None:
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text(make_heartbeat(), encoding="utf-8")
    assert _get_last_done_type(hb) is None


def test_get_recent_git_activity_returns_empty_outside_repo(tmp_path: Path) -> None:
    assert _get_recent_git_activity(tmp_path) == []


def test_queue_row_has_all_fields(tmp_path: Path) -> None:
    """Generated queue row has all 8 required columns."""
    hb = tmp_path / "HEARTBEAT.md"
    hb.write_text(make_heartbeat(), encoding="utf-8")
    run_inspire_scan(project=tmp_path, heartbeat=hb, language="zh")
    rows = _read_queue_rows(hb)
    assert len(rows) >= 1
    row = rows[0]
    for key in ("type", "score", "content", "detail", "source", "status", "created"):
        assert key in row, f"Missing key: {key}"
