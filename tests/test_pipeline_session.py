"""Tests for PipelineSession and pipeline timing persistence."""

import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from refactron.core.pipeline import RefactronPipeline
from refactron.core.pipeline_session import PipelineSession
from refactron.core.models import CodeIssue, IssueCategory, IssueLevel


def test_session_initialization():
    """Test that PipelineSession initializes with default values."""
    session = PipelineSession()
    assert session.id
    assert session.analyze_ms == 0.0
    assert session.queue_ms == 0.0
    assert session.apply_ms == 0.0
    assert session.verify_ms == 0.0
    assert isinstance(session.metadata, dict)


def test_session_serialization():
    """Test that PipelineSession can be converted to and from a dictionary."""
    session = PipelineSession(analyze_ms=10.5, queue_ms=5.2)
    data = session.to_dict()
    assert data["analyze_ms"] == 10.5
    assert data["queue_ms"] == 5.2

    new_session = PipelineSession.from_dict(data)
    assert new_session.id == session.id
    assert new_session.analyze_ms == 10.5


def test_pipeline_timing_integration():
    """Test that RefactronPipeline populates session timings."""
    with patch("refactron.core.pipeline.Refactron.analyze") as mock_analyze:
        mock_analyze.return_value = MagicMock(all_issues=[])

        pipeline = RefactronPipeline()

        # 1. Analyze
        pipeline.analyze(Path("."))
        assert pipeline.session.analyze_ms > 0

        # 2. Queue
        issue = CodeIssue(
            category=IssueCategory.STYLE,
            level=IssueLevel.INFO,
            message="Test",
            file_path=Path("test.py"),
            line_number=1,
        )
        pipeline.queue_issues([issue])
        assert pipeline.session.queue_ms > 0


def test_pipeline_apply_verify_timings():
    """Test that apply and verify phases record timings."""
    pipeline = RefactronPipeline()

    # Mock apply logic
    pipeline.autofix_engine.fix = MagicMock(return_value=MagicMock(success=True, fixed_code=""))

    with patch.object(Path, "read_text", return_value="code"):
        with patch.object(Path, "write_text"):
            issue = MagicMock(spec=CodeIssue)
            issue.file_path = Path("test.py")
            pipeline.apply([{"issue": issue, "fixer_name": "test"}])
            assert pipeline.session.apply_ms > 0

    with patch.object(RefactronPipeline, "analyze", return_value=MagicMock()):
        pipeline.verify(Path("."))
        assert pipeline.session.verify_ms > 0


def test_pipeline_apply_multi_file_best_effort():
    """Test best-effort behavior (continues on failure)."""
    pipeline = RefactronPipeline()

    # Mock fixers
    success_fix = MagicMock(success=True, fixed_code="fixed")
    fail_fix = MagicMock(success=False, reason="Blocked")

    pipeline.autofix_engine.fix = MagicMock(side_effect=[success_fix, fail_fix])

    issue1 = CodeIssue(
        category=IssueCategory.STYLE,
        level=IssueLevel.INFO,
        message="Succeed",
        file_path=Path("success.py"),
        line_number=1,
    )
    issue2 = CodeIssue(
        category=IssueCategory.STYLE,
        level=IssueLevel.INFO,
        message="Fail",
        file_path=Path("fail.py"),
        line_number=1,
    )

    with patch.object(Path, "read_text", return_value="original"):
        with patch.object(Path, "write_text"):
            with patch("refactron.core.pipeline.BackupRollbackSystem") as mock_backup:
                mock_backup.return_value.prepare_for_refactoring.return_value = ("backup_123", [])

                pipeline.apply(
                    [
                        {"issue": issue1, "fixer_name": "fix1"},
                        {"issue": issue2, "fixer_name": "fix2"},
                    ],
                    fail_fast=False,
                )

    assert pipeline.session.files_attempted == 2
    assert pipeline.session.files_succeeded == 1
    assert pipeline.session.files_failed == 1
    assert len(pipeline.session.blocked_fixes) == 1
    assert pipeline.session.backup_session_id == "backup_123"


def test_pipeline_apply_fail_fast():
    """Test fail-fast behavior (stops on first failure)."""
    pipeline = RefactronPipeline()

    # Mock fixers
    fail_fix = MagicMock(success=False, reason="Blocked")
    success_fix = MagicMock(success=True, fixed_code="fixed")

    pipeline.autofix_engine.fix = MagicMock(side_effect=[fail_fix, success_fix])

    # Note: file_map depends on dict order or hash?
    # Usually we want to ensure fail.py is processed first for this test.
    # Grouping by file path.

    issue1 = CodeIssue(
        category=IssueCategory.STYLE,
        level=IssueLevel.INFO,
        message="Fail",
        file_path=Path("a_fail.py"),
        line_number=1,
    )
    issue2 = CodeIssue(
        category=IssueCategory.STYLE,
        level=IssueLevel.INFO,
        message="Succeed",
        file_path=Path("b_success.py"),
        line_number=1,
    )

    with patch.object(Path, "read_text", return_value="original"):
        with patch.object(Path, "write_text"):
            pipeline.apply(
                [{"issue": issue1, "fixer_name": "fix1"}, {"issue": issue2, "fixer_name": "fix2"}],
                fail_fast=True,
            )

    # Should stop after first failure (a_fail.py)
    assert pipeline.session.files_failed == 1
    assert pipeline.session.files_succeeded == 0
    # The second file should not have been attempted successfully
    # Wait, files_attempted is calculated at start.
    assert pipeline.session.files_attempted == 2


def test_session_persistence():
    """Test that PipelineSession can be saved and loaded from disk."""
    import tempfile
    import json

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        session = PipelineSession(analyze_ms=100.0)
        session_id = session.id

        # Save
        save_path = session.save(directory=temp_path)
        assert save_path.exists()
        assert save_path.name == f"{session_id}.json"

        # Check latest pointer
        latest_path = temp_path / "latest.json"
        assert latest_path.exists()
        with open(latest_path, "r") as f:
            latest_data = json.load(f)
            assert latest_data["latest_session_id"] == session_id

        # Load
        loaded_session = PipelineSession.from_id(session_id, directory=temp_path)
        assert loaded_session is not None
        assert loaded_session.id == session_id
        assert loaded_session.analyze_ms == 100.0


def test_pipeline_save_session_integration():
    """Test that RefactronPipeline.save_session works."""
    import tempfile

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        pipeline = RefactronPipeline()
        pipeline.session.analyze_ms = 50.0

        save_path = pipeline.save_session(directory=temp_path)
        assert save_path.exists()

        loaded = PipelineSession.from_id(pipeline.session.id, directory=temp_path)
        assert loaded.analyze_ms == 50.0
