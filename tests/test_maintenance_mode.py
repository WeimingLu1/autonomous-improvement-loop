"""Tests for maintenance mode tag-based deduplication."""

import pytest

from scripts.task_planner import (
    _maintenance_tag_versions,
    _maintenance_candidate_title,
    _MAINTENANCE_CANDIDATES,
)
from scripts.roadmap import _parse_done_log_entries


class TestMaintenanceTagVersions:
    """Tests for _maintenance_tag_versions()."""

    def test_empty_log_returns_empty_dict(self):
        result = _maintenance_tag_versions([])
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

    def test_unknown_keys_still_counted(self):
        entries = [
            {"tag": "security", "title": "审计1"},
            {"tag": "unknown-tag", "title": "未知1"},
        ]
        result = _maintenance_tag_versions(entries)
        assert result == {"security": 1, "unknown-tag": 1}


class TestMaintenanceCandidateTitle:
    """Tests for _maintenance_candidate_title()."""

    def test_version_1_returns_original(self):
        candidate = {"title": "进行安全漏洞审计"}
        assert _maintenance_candidate_title(candidate, 1) == "进行安全漏洞审计"

    def test_version_2_adds_v2_suffix(self):
        candidate = {"title": "进行安全漏洞审计"}
        assert _maintenance_candidate_title(candidate, 2) == "进行安全漏洞审计 v2"

    def test_version_3_adds_v3_suffix(self):
        candidate = {"title": "补充单元测试覆盖"}
        assert _maintenance_candidate_title(candidate, 3) == "补充单元测试覆盖 v3"

    def test_version_0_returns_original(self):
        candidate = {"title": "清理无用代码"}
        assert _maintenance_candidate_title(candidate, 0) == "清理无用代码"


class TestDoneLogTagSchema:
    """Tests for Done Log tag schema parsing."""

    def test_parse_new_format_with_tag(self):
        """New 8-column format parses correctly."""
        block = "| time | task_id | type | source | tag | title | result | commit |\n| 2026-04-25 | TASK-001 | maintenance | pm | security | 进行安全漏洞审计 | pass | abc123 |\n"
        entries = _parse_done_log_entries(block)
        assert len(entries) == 1
        assert entries[0]["tag"] == "security"
        assert entries[0]["title"] == "进行安全漏洞审计"
        assert entries[0]["task_type"] == "maintenance"

    def test_parse_old_format_without_tag(self):
        """Legacy 7-column format (no tag) parses with empty tag."""
        old_block = "| time | task_id | type | source | title | result | commit |\n| 2026-04-24 | TASK-001 | idea | pm | Some task | pass | abc123 |\n"
        entries = _parse_done_log_entries(old_block)
        assert len(entries) == 1
        assert entries[0]["tag"] == ""
        assert entries[0]["title"] == "Some task"

    def test_parse_mixed_format(self):
        """Mix of old and new rows parses correctly."""
        block = (
            "| time | task_id | type | source | tag | title | result | commit |\n"
            "| 2026-04-24 | TASK-001 | idea | pm | | Old idea | pass | abc |\n"
            "| 2026-04-25 | TASK-002 | maintenance | pm | security | 审计v2 | pass | def |\n"
        )
        entries = _parse_done_log_entries(block)
        assert len(entries) == 2
        assert entries[0]["tag"] == ""
        assert entries[1]["tag"] == "security"

    def test_multiple_entries_with_same_tag(self):
        """Same tag appearing multiple times is counted correctly."""
        block = (
            "| time | task_id | type | source | tag | title | result | commit |\n"
            "| 2026-04-25 | TASK-001 | maintenance | pm | security | 审计v2 | pass | a |\n"
            "| 2026-04-25 | TASK-002 | maintenance | pm | security | 审计v3 | pass | b |\n"
            "| 2026-04-25 | TASK-003 | maintenance | pm | testing | 测试v2 | pass | c |\n"
        )
        entries = _parse_done_log_entries(block)
        versions = _maintenance_tag_versions(entries)
        assert versions == {"security": 2, "testing": 1}


class TestMaintenanceCandidatesHaveTags:
    """Verify all _MAINTENANCE_CANDIDATES have maintenance_tag set."""

    def test_all_candidates_have_tag(self):
        """Every maintenance candidate should have a maintenance_tag."""
        for c in _MAINTENANCE_CANDIDATES:
            assert "maintenance_tag" in c, f"Candidate '{c['title']}' missing maintenance_tag"
            assert c["maintenance_tag"], f"Candidate '{c['title']}' has empty maintenance_tag"

    def test_tags_are_unique_enough(self):
        """Tags should provide good coverage across maintenance categories."""
        tags = [c["maintenance_tag"] for c in _MAINTENANCE_CANDIDATES]
        unique_tags = set(tags)
        # At least 8 different tag categories expected
        assert len(unique_tags) >= 8, f"Only {len(unique_tags)} unique tags: {unique_tags}"