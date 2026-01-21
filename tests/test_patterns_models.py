"""Tests for Pattern Learning System models."""

from datetime import datetime
from pathlib import Path

import pytest

from refactron.patterns.models import (
    PatternMetric,
    ProjectPatternProfile,
    RefactoringFeedback,
    RefactoringPattern,
)


class TestRefactoringFeedback:
    """Tests for RefactoringFeedback model."""

    def test_feedback_creation(self) -> None:
        """Test creating a feedback record."""
        feedback = RefactoringFeedback.create(
            operation_id="op-123",
            operation_type="extract_method",
            file_path=Path("test.py"),
            action="accepted",
            code_pattern_hash="abc123",
            reason="Improved readability",
        )

        assert feedback.operation_id == "op-123"
        assert feedback.operation_type == "extract_method"
        assert feedback.action == "accepted"
        assert feedback.code_pattern_hash == "abc123"
        assert feedback.reason == "Improved readability"
        assert isinstance(feedback.timestamp, datetime)

    def test_feedback_serialization(self) -> None:
        """Test feedback serialization to/from dict."""
        feedback = RefactoringFeedback.create(
            operation_id="op-123",
            operation_type="extract_method",
            file_path=Path("test.py"),
            action="accepted",
            code_pattern_hash="abc123",
        )

        # Convert to dict
        data = feedback.to_dict()
        assert "operation_id" in data
        assert "timestamp" in data
        assert isinstance(data["timestamp"], str)

        # Convert back from dict
        feedback2 = RefactoringFeedback.from_dict(data)
        assert feedback2.operation_id == feedback.operation_id
        assert feedback2.operation_type == feedback.operation_type
        assert feedback2.action == feedback.action
        assert isinstance(feedback2.timestamp, datetime)

    def test_feedback_with_project_path(self) -> None:
        """Test feedback with project path."""
        project_path = Path("/project/root")
        feedback = RefactoringFeedback.create(
            operation_id="op-123",
            operation_type="extract_method",
            file_path=Path("test.py"),
            action="accepted",
            project_path=project_path,
        )

        assert feedback.project_path == project_path

        # Test serialization
        data = feedback.to_dict()
        assert "project_path" in data

        feedback2 = RefactoringFeedback.from_dict(data)
        assert feedback2.project_path == project_path


class TestRefactoringPattern:
    """Tests for RefactoringPattern model."""

    def test_pattern_creation(self) -> None:
        """Test creating a pattern."""
        pattern = RefactoringPattern.create(
            pattern_hash="hash123",
            operation_type="extract_method",
            code_snippet_before="def foo():\n    x = 1\n    return x",
            code_snippet_after="CONSTANT = 1\n\ndef foo():\n    return CONSTANT",
        )

        assert pattern.pattern_hash == "hash123"
        assert pattern.operation_type == "extract_method"
        assert pattern.total_occurrences == 0
        assert pattern.acceptance_rate == 0.0
        assert isinstance(pattern.pattern_id, str)
        assert len(pattern.pattern_id) > 0

    def test_pattern_update_from_feedback(self) -> None:
        """Test updating pattern statistics from feedback."""
        pattern = RefactoringPattern.create(
            pattern_hash="hash123",
            operation_type="extract_method",
            code_snippet_before="before",
            code_snippet_after="after",
        )

        # Update with accepted
        pattern.update_from_feedback("accepted")
        assert pattern.total_occurrences == 1
        assert pattern.accepted_count == 1
        assert pattern.rejected_count == 0
        assert pattern.acceptance_rate == 1.0

        # Update with rejected
        pattern.update_from_feedback("rejected")
        assert pattern.total_occurrences == 2
        assert pattern.accepted_count == 1
        assert pattern.rejected_count == 1
        assert pattern.acceptance_rate == 0.5

        # Update with ignored
        pattern.update_from_feedback("ignored")
        assert pattern.total_occurrences == 3
        assert pattern.ignored_count == 1
        assert pattern.acceptance_rate == 0.5  # Should not change

    def test_pattern_serialization(self) -> None:
        """Test pattern serialization to/from dict."""
        pattern = RefactoringPattern.create(
            pattern_hash="hash123",
            operation_type="extract_method",
            code_snippet_before="before",
            code_snippet_after="after",
        )

        pattern.update_from_feedback("accepted")

        # Convert to dict
        data = pattern.to_dict()
        assert "pattern_id" in data
        assert "first_seen" in data
        assert isinstance(data["first_seen"], str)

        # Convert back from dict
        pattern2 = RefactoringPattern.from_dict(data)
        assert pattern2.pattern_id == pattern.pattern_id
        assert pattern2.total_occurrences == pattern.total_occurrences
        assert pattern2.acceptance_rate == pattern.acceptance_rate

    def test_pattern_benefit_score(self) -> None:
        """Test pattern benefit score calculation."""
        pattern = RefactoringPattern.create(
            pattern_hash="hash123",
            operation_type="extract_method",
            code_snippet_before="before",
            code_snippet_after="after",
        )
        pattern.acceptance_rate = 0.8

        metric = PatternMetric(
            pattern_id=pattern.pattern_id,
            complexity_reduction=5.0,
            maintainability_improvement=20.0,
            issue_resolution_count=3,
        )

        score = pattern.calculate_benefit_score(metric)
        assert 0.0 <= score <= 1.0


class TestPatternMetric:
    """Tests for PatternMetric model."""

    def test_metric_creation(self) -> None:
        """Test creating a metric."""
        metric = PatternMetric(
            pattern_id="pattern-123",
            complexity_reduction=2.5,
            maintainability_improvement=10.0,
            lines_of_code_change=-5,
            issue_resolution_count=2,
        )

        assert metric.pattern_id == "pattern-123"
        assert metric.complexity_reduction == 2.5
        assert metric.maintainability_improvement == 10.0
        assert metric.lines_of_code_change == -5
        assert metric.issue_resolution_count == 2

    def test_metric_update(self) -> None:
        """Test updating metric with new evaluation."""
        metric = PatternMetric(
            pattern_id="pattern-123",
            complexity_reduction=2.0,
            maintainability_improvement=10.0,
            lines_of_code_change=-3,
            issue_resolution_count=1,
        )

        # First update (should replace initial values)
        metric.update(
            complexity_reduction=4.0,
            maintainability_improvement=20.0,
            lines_of_code_change=-5,
            issue_resolution_count=2,
            before_metrics={"complexity": 10.0},
            after_metrics={"complexity": 6.0},
        )

        assert metric.total_evaluations == 1
        # First update: weight = 1.0, so it should be exactly the new value
        assert metric.complexity_reduction == 4.0
        assert metric.maintainability_improvement == 20.0
        assert metric.issue_resolution_count == 3  # 1 + 2
        assert "complexity" in metric.before_metrics
        assert "complexity" in metric.after_metrics

        # Second update (should calculate weighted average)
        metric.update(
            complexity_reduction=6.0,
            maintainability_improvement=30.0,
            lines_of_code_change=-7,
            issue_resolution_count=1,
            before_metrics={"complexity": 12.0},
            after_metrics={"complexity": 8.0},
        )

        assert metric.total_evaluations == 2
        # Second update: weight = 0.5, so should be average of 4.0 and 6.0
        assert metric.complexity_reduction == 5.0
        assert metric.maintainability_improvement == 25.0

    def test_metric_serialization(self) -> None:
        """Test metric serialization to/from dict."""
        metric = PatternMetric(
            pattern_id="pattern-123",
            complexity_reduction=2.5,
            maintainability_improvement=10.0,
        )

        data = metric.to_dict()
        assert "pattern_id" in data
        assert data["complexity_reduction"] == 2.5

        metric2 = PatternMetric.from_dict(data)
        assert metric2.pattern_id == metric.pattern_id
        assert metric2.complexity_reduction == metric.complexity_reduction


class TestProjectPatternProfile:
    """Tests for ProjectPatternProfile model."""

    def test_profile_creation(self) -> None:
        """Test creating a project profile."""
        project_path = Path("/project/root")
        profile = ProjectPatternProfile.create(project_path)

        assert profile.project_path == project_path
        assert isinstance(profile.project_id, str)
        assert len(profile.project_id) > 0

    def test_profile_id_stability(self) -> None:
        """Test that project ID is stable for same path."""
        project_path = Path("/project/root")
        profile1 = ProjectPatternProfile.create(project_path)
        profile2 = ProjectPatternProfile.create(project_path)

        assert profile1.project_id == profile2.project_id

    def test_enable_disable_pattern(self) -> None:
        """Test enabling and disabling patterns."""
        profile = ProjectPatternProfile.create(Path("/project"))

        profile.enable_pattern("pattern-1")
        assert "pattern-1" in profile.enabled_patterns
        assert profile.is_pattern_enabled("pattern-1")

        profile.disable_pattern("pattern-1")
        assert "pattern-1" in profile.disabled_patterns
        assert not profile.is_pattern_enabled("pattern-1")

        # Disabling should remove from enabled
        profile.enable_pattern("pattern-2")
        profile.disable_pattern("pattern-2")
        assert "pattern-2" not in profile.enabled_patterns
        assert "pattern-2" in profile.disabled_patterns

    def test_pattern_weight(self) -> None:
        """Test setting and getting pattern weights."""
        profile = ProjectPatternProfile.create(Path("/project"))

        profile.set_pattern_weight("pattern-1", 0.7)
        assert profile.get_pattern_weight("pattern-1") == 0.7
        assert profile.get_pattern_weight("pattern-2") == 1.0  # Default

        # Test invalid weight
        with pytest.raises(ValueError):
            profile.set_pattern_weight("pattern-1", 1.5)

        with pytest.raises(ValueError):
            profile.set_pattern_weight("pattern-1", -0.5)

    def test_rule_threshold(self) -> None:
        """Test setting rule thresholds."""
        profile = ProjectPatternProfile.create(Path("/project"))

        profile.set_rule_threshold("complexity", 15.0)
        assert profile.rule_thresholds["complexity"] == 15.0

    def test_pattern_enabled_logic(self) -> None:
        """Test pattern enabled logic."""
        profile = ProjectPatternProfile.create(Path("/project"))

        # Default: all enabled if no restrictions
        assert profile.is_pattern_enabled("any-pattern")

        # If disabled, should be disabled
        profile.disable_pattern("pattern-1")
        assert not profile.is_pattern_enabled("pattern-1")

        # If enabled list exists, only those are enabled
        profile.enable_pattern("pattern-2")
        profile.enable_pattern("pattern-3")
        assert profile.is_pattern_enabled("pattern-2")
        assert profile.is_pattern_enabled("pattern-3")
        assert not profile.is_pattern_enabled("pattern-4")

    def test_profile_serialization(self) -> None:
        """Test profile serialization to/from dict."""
        profile = ProjectPatternProfile.create(Path("/project/root"))
        profile.enable_pattern("pattern-1")
        profile.set_pattern_weight("pattern-2", 0.8)

        data = profile.to_dict()
        assert "project_id" in data
        assert "project_path" in data
        assert isinstance(data["project_path"], str)
        assert isinstance(data["enabled_patterns"], list)

        profile2 = ProjectPatternProfile.from_dict(data)
        assert profile2.project_id == profile.project_id
        assert profile2.enabled_patterns == profile.enabled_patterns
        assert profile2.pattern_weights == profile.pattern_weights
