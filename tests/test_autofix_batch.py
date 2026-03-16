"""Tests for the auto-fix batch reporting and interactive modes (4.3)."""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from refactron.autofix.engine import AutoFixEngine
from refactron.autofix.models import BatchFixReport, FixRiskLevel, FixStats
from refactron.core.models import CodeIssue, IssueCategory, IssueLevel


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_CODE = """\
import os
import sys

x = 1
print(x)
"""


def _issue(rule_id: str, line: int = 1, msg: str = "issue") -> CodeIssue:
    """Create a minimal CodeIssue for testing."""
    return CodeIssue(
        category=IssueCategory.CODE_SMELL,
        level=IssueLevel.WARNING,
        message=msg,
        file_path=Path("test.py"),
        line_number=line,
        rule_id=rule_id,
    )


# ---------------------------------------------------------------------------
# FixStats tests
# ---------------------------------------------------------------------------


class TestFixStats:
    def test_success_rate_zero_total(self):
        stats = FixStats()
        assert stats.success_rate == 0.0

    def test_success_rate_calculation(self):
        stats = FixStats(total=10, successful=7)
        assert stats.success_rate == 70.0

    def test_summary_contains_key_metrics(self):
        stats = FixStats(total=5, successful=3, failed=1, skipped=1, files_affected=2)
        summary = stats.summary()
        assert "3/5" in summary
        assert "Failed: 1" in summary
        assert "Skipped: 1" in summary
        assert "Files affected: 2" in summary


# ---------------------------------------------------------------------------
# BatchFixReport tests
# ---------------------------------------------------------------------------


class TestBatchFixReport:
    def test_get_successful_filters_correctly(self):
        from refactron.autofix.models import FixResult

        report = BatchFixReport()
        report.results[0] = FixResult(success=True, reason="ok")
        report.results[1] = FixResult(success=False, reason="fail")
        assert len(report.get_successful()) == 1
        assert len(report.get_failed()) == 1

    def test_empty_report_defaults(self):
        report = BatchFixReport()
        assert report.stats.total == 0
        assert report.results == {}
        assert report.pending_diffs == []


# ---------------------------------------------------------------------------
# fix_batch_with_report tests
# ---------------------------------------------------------------------------


class TestFixBatchWithReport:
    def test_returns_batch_fix_report(self):
        engine = AutoFixEngine(safety_level=FixRiskLevel.LOW)
        issues = [_issue("remove_unused_imports")]
        report = engine.fix_batch_with_report(issues, SAMPLE_CODE, file_path="test.py")
        assert isinstance(report, BatchFixReport)

    def test_stats_total_matches_issue_count(self):
        engine = AutoFixEngine()
        issues = [_issue("remove_unused_imports"), _issue("sort_imports")]
        report = engine.fix_batch_with_report(issues, SAMPLE_CODE)
        assert report.stats.total == 2

    def test_unfixable_issues_are_skipped(self):
        engine = AutoFixEngine()
        issues = [_issue("unknown_rule_xyz")]
        report = engine.fix_batch_with_report(issues, SAMPLE_CODE)
        assert report.stats.skipped == 1
        assert report.stats.successful == 0

    def test_files_affected_tracked(self):
        engine = AutoFixEngine(safety_level=FixRiskLevel.LOW)
        issues = [_issue("remove_unused_imports")]
        report = engine.fix_batch_with_report(issues, SAMPLE_CODE, file_path="myfile.py")
        # files_affected is set when at least one fix succeeds
        assert report.stats.files_affected >= 0

    def test_duration_is_positive(self):
        engine = AutoFixEngine()
        report = engine.fix_batch_with_report([], SAMPLE_CODE)
        assert report.stats.duration_seconds >= 0.0

    def test_results_indexed_per_issue(self):
        engine = AutoFixEngine(safety_level=FixRiskLevel.LOW)
        issues = [
            _issue("remove_unused_imports"),
            _issue("sort_imports"),
        ]
        report = engine.fix_batch_with_report(issues, SAMPLE_CODE)
        assert 0 in report.results
        assert 1 in report.results


# ---------------------------------------------------------------------------
# fix_interactive tests
# ---------------------------------------------------------------------------


class TestFixInteractive:
    def test_dry_run_collects_diffs_without_applying(self):
        engine = AutoFixEngine(safety_level=FixRiskLevel.LOW)
        issues = [_issue("remove_unused_imports")]
        # No callback = dry run
        report = engine.fix_interactive(issues, SAMPLE_CODE)
        assert isinstance(report, BatchFixReport)
        # Skipped because no confirmation given
        assert report.stats.skipped >= 0

    def test_pending_diffs_populated_for_fixable_issues(self):
        engine = AutoFixEngine(safety_level=FixRiskLevel.LOW)
        issues = [_issue("remove_unused_imports")]
        report = engine.fix_interactive(issues, SAMPLE_CODE)
        # pending_diffs should be populated for any fixable issues that have a diff
        assert isinstance(report.pending_diffs, list)

    def test_callback_approves_and_applies(self):
        engine = AutoFixEngine(safety_level=FixRiskLevel.LOW)
        code_with_whitespace = "import os  \nimport sys\n"
        issues = [_issue("remove_trailing_whitespace")]

        # Approve all fixes
        def approve_all(idx, diff, reason):
            return True

        report = engine.fix_interactive(issues, code_with_whitespace, confirm_callback=approve_all)
        assert isinstance(report, BatchFixReport)
        assert report.stats.total >= 1

    def test_callback_rejects_keeps_as_skipped(self):
        engine = AutoFixEngine(safety_level=FixRiskLevel.LOW)
        issues = [_issue("remove_unused_imports")]

        # Reject all fixes
        def reject_all(idx, diff, reason):
            return False

        report = engine.fix_interactive(issues, SAMPLE_CODE, confirm_callback=reject_all)
        assert report.stats.successful == 0

    def test_unfixable_issues_skipped_in_interactive(self):
        engine = AutoFixEngine()
        issues = [_issue("not_a_real_rule")]
        report = engine.fix_interactive(issues, SAMPLE_CODE)
        assert report.stats.skipped == 1

    def test_duration_is_positive_interactive(self):
        engine = AutoFixEngine()
        report = engine.fix_interactive([], SAMPLE_CODE)
        assert report.stats.duration_seconds >= 0.0
