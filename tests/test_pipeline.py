"""Tests for the Refactron pipeline module."""

import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock

from refactron.core.pipeline import RefactronPipeline
from refactron.core.config import RefactronConfig


def test_pipeline_loads_project_config():
    """Test that RefactronPipeline loads configuration from the project root."""
    with tempfile.TemporaryDirectory() as temp_dir:
        root_path = Path(temp_dir)

        config_path = root_path / ".refactron.yaml"
        config_path.write_text("max_function_complexity: 99\nenable_metrics: false\n")

        target_file = root_path / "dummy.py"
        target_file.write_text("def foo():\n    pass\n")

        with patch("refactron.core.pipeline.Refactron.analyze") as mock_analyze:
            mock_analyze.return_value = "mock_result"
            pipeline = RefactronPipeline(project_root=root_path)

            result = pipeline.analyze(target_file)

            assert result == "mock_result"
            config_passed = pipeline.refactron.config

            assert isinstance(config_passed, RefactronConfig)
            assert config_passed.max_function_complexity == 99
            assert config_passed.enable_metrics is False
            assert config_passed.enable_incremental_analysis is False


def test_pipeline_incremental_override():
    """Test that RefactronPipeline can override the incremental setting."""
    with tempfile.TemporaryDirectory() as temp_dir:
        root_path = Path(temp_dir)

        target_file = root_path / "dummy.py"
        target_file.write_text("def foo():\n    pass\n")

        with patch("refactron.core.pipeline.Refactron.analyze"):
            pipeline = RefactronPipeline(project_root=root_path)
            pipeline.analyze(target_file, use_incremental=True)

            config_passed = pipeline.refactron.config
            assert config_passed.enable_incremental_analysis is True


def test_pipeline_queue_issues_caching():
    """Test that queue_issues leverages caching and direct mapping without multiple previews."""
    from refactron.core.models import CodeIssue, IssueCategory, IssueLevel
    from refactron.autofix.models import FixResult
    from pathlib import Path

    with tempfile.TemporaryDirectory() as temp_dir:
        pipeline = RefactronPipeline(project_root=Path(temp_dir))

        # Mock AutoFixEngine on the pipeline directly
        pipeline.autofix_engine = MagicMock()

        calls = {"preview": 0}

        # Create a mock fixer that counts preview calls
        mock_fixer = MagicMock()
        mock_fixer.name = "mock_rule"

        def mock_preview(issue, code):
            calls["preview"] += 1
            return FixResult(success=True, reason="")

        mock_fixer.preview.side_effect = mock_preview

        pipeline.autofix_engine.fixers = {"mock_rule": mock_fixer}

        # Mock can_fix to return False so it falls back to preview ONCE per type
        pipeline.autofix_engine.can_fix.return_value = False

        issue1 = CodeIssue(
            category=IssueCategory.STYLE,
            level=IssueLevel.WARNING,
            message="Test issue",
            file_path=Path("dummy.py"),
            line_number=1,
            rule_id="unknown_rule_1",
        )
        issue2 = CodeIssue(
            category=IssueCategory.STYLE,
            level=IssueLevel.WARNING,
            message="Test issue 2",
            file_path=Path("dummy.py"),
            line_number=2,
            rule_id="unknown_rule_1",
        )
        issue3 = CodeIssue(
            category=IssueCategory.STYLE,
            level=IssueLevel.WARNING,
            message="Test issue 3",
            file_path=Path("dummy.py"),
            line_number=3,
            rule_id="unknown_rule_1",
        )

        queued = pipeline.queue_issues([issue1, issue2, issue3])

        assert len(queued) == 3
        # Should only have run preview 1 time, because the subsequent issues have the same rule_id and hit the cache.
        assert calls["preview"] == 1
        assert pipeline._fixer_cache["unknown_rule_1"] == "mock_rule"
