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
            line_number=1
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
