"""
Phase 4 End-to-End Tests: AI Suppression Memorization & Manual Override.

These tests validate:
1. PatternLearner stores "suppressed_by_ai" feedback correctly.
2. PatternMatcher drops issues locally before hitting the LLM API (cache check).
3. A manual "accepted_as_smell" override permanently bypasses AI suppression.
"""

import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from refactron.core.config import RefactronConfig
from refactron.core.models import CodeIssue, IssueCategory, IssueLevel, RefactoringOperation
from refactron.patterns.fingerprint import PatternFingerprinter
from refactron.patterns.learner import PatternLearner
from refactron.patterns.matcher import PatternMatcher
from refactron.patterns.models import RefactoringFeedback
from refactron.patterns.storage import PatternStorage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def storage(tmp_path):
    """Create a fresh PatternStorage backed by a temp directory."""
    return PatternStorage(storage_dir=tmp_path)


@pytest.fixture
def fingerprinter():
    return PatternFingerprinter()


@pytest.fixture
def learner(storage, fingerprinter):
    return PatternLearner(storage=storage, fingerprinter=fingerprinter)


@pytest.fixture
def matcher(storage):
    return PatternMatcher(storage=storage)


@pytest.fixture
def sample_issue(tmp_path):
    """A simple CodeIssue representing a code smell."""
    code_file = tmp_path / "smelly.py"
    code_file.write_text('def too_many_params(a, b, c, d, e, f, g):\n    """Sample docstring."""\n    return a\n')
    return CodeIssue(
        category=IssueCategory.CODE_SMELL,
        level=IssueLevel.WARNING,
        message="Too many parameters",
        file_path=code_file,
        line_number=1,
        rule_id="S001",
    )


@pytest.fixture
def source_code():
    return 'def too_many_params(a, b, c, d, e, f, g):\n    """Sample docstring."""\n    return a\n'


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_operation_and_feedback(issue, fingerprint, action, source_code):
    """Create a RefactoringOperation + RefactoringFeedback pair for the learner."""
    op = RefactoringOperation(
        operation_type="code_smell",
        file_path=issue.file_path,
        line_number=issue.line_number,
        description=issue.message,
        old_code=source_code.split("\n")[issue.line_number - 1],
        new_code="",
        risk_score=0.5,
        metadata={"code_pattern_hash": fingerprint},
    )
    feedback = RefactoringFeedback.create(
        operation_id=op.operation_id,
        operation_type=op.operation_type,
        file_path=issue.file_path,
        action=action,
        code_pattern_hash=fingerprint,
    )
    return op, feedback


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestPatternLearnerStoresSuppression:
    """AC1: PatternLearner must accept and store 'suppressed_by_ai' feedback."""

    def test_learn_from_suppressed_by_ai_feedback(
        self, learner, storage, fingerprinter, sample_issue, source_code
    ):
        fingerprint = fingerprinter.fingerprint_issue_context(sample_issue, source_code)
        op, feedback = _make_operation_and_feedback(
            sample_issue, fingerprint, "suppressed_by_ai", source_code
        )

        pattern_id = learner.learn_from_feedback(op, feedback)

        assert pattern_id is not None, "learn_from_feedback should return a pattern_id"

        patterns = storage.load_patterns()
        assert len(patterns) == 1, "Exactly one pattern should be stored"

        pattern = patterns[pattern_id]
        assert pattern.suppressed_count == 1, "suppressed_count should be incremented"
        assert pattern.overruled_count == 0, "No overrule yet"
        assert pattern.pattern_hash == fingerprint

    def test_suppressed_count_increments_on_repeated_suppression(
        self, learner, storage, fingerprinter, sample_issue, source_code
    ):
        fingerprint = fingerprinter.fingerprint_issue_context(sample_issue, source_code)

        for _ in range(3):
            op, feedback = _make_operation_and_feedback(
                sample_issue, fingerprint, "suppressed_by_ai", source_code
            )
            learner.learn_from_feedback(op, feedback)
            # Clear storage cache so next call re-reads from disk
            storage._patterns_cache = None

        patterns = storage.load_patterns()
        assert len(patterns) == 1, "All suppressions map to the same pattern"
        pattern = list(patterns.values())[0]
        assert pattern.suppressed_count == 3


class TestPatternMatcherDropsSuppressedIssues:
    """AC2: PatternMatcher must return True for suppressed fingerprints."""

    def test_not_suppressed_when_no_patterns(self, matcher, fingerprinter, sample_issue, source_code):
        fingerprint = fingerprinter.fingerprint_issue_context(sample_issue, source_code)
        assert matcher.is_suppressed_by_ai(fingerprint) is False

    def test_suppressed_after_learning(
        self, learner, matcher, fingerprinter, sample_issue, source_code, storage
    ):
        fingerprint = fingerprinter.fingerprint_issue_context(sample_issue, source_code)
        op, feedback = _make_operation_and_feedback(
            sample_issue, fingerprint, "suppressed_by_ai", source_code
        )
        learner.learn_from_feedback(op, feedback)

        # Clear matcher cache so it reloads from storage
        matcher.clear_cache()

        assert matcher.is_suppressed_by_ai(fingerprint) is True

    def test_not_suppressed_when_overruled_exceeds_suppressed(
        self, learner, matcher, fingerprinter, sample_issue, source_code, storage
    ):
        fingerprint = fingerprinter.fingerprint_issue_context(sample_issue, source_code)

        # Record one suppression
        op, feedback = _make_operation_and_feedback(
            sample_issue, fingerprint, "suppressed_by_ai", source_code
        )
        learner.learn_from_feedback(op, feedback)
        storage._patterns_cache = None
        matcher.clear_cache()

        assert matcher.is_suppressed_by_ai(fingerprint) is True

        # Record one manual override — overruled_count becomes suppressed_count+1
        op2, feedback2 = _make_operation_and_feedback(
            sample_issue, fingerprint, "accepted_as_smell", source_code
        )
        learner.learn_from_feedback(op2, feedback2)
        storage._patterns_cache = None
        matcher.clear_cache()

        assert matcher.is_suppressed_by_ai(fingerprint) is False


class TestManualOverridePermanentlyBypassesSuppression:
    """
    AC5 (main): After a user applies 'accepted_as_smell', the issue must no longer
    be suppressed — even if the LLM would have suppressed it again.
    """

    def test_full_suppress_then_override_cycle(
        self, learner, matcher, fingerprinter, sample_issue, source_code, storage
    ):
        fingerprint = fingerprinter.fingerprint_issue_context(sample_issue, source_code)

        # --- Step 1: AI suppresses the issue ---
        op1, fb1 = _make_operation_and_feedback(
            sample_issue, fingerprint, "suppressed_by_ai", source_code
        )
        learner.learn_from_feedback(op1, fb1)
        storage._patterns_cache = None
        matcher.clear_cache()
        assert matcher.is_suppressed_by_ai(fingerprint) is True, "Should be suppressed after AI decision"

        # --- Step 2: User manually overrides ---
        op2, fb2 = _make_operation_and_feedback(
            sample_issue, fingerprint, "accepted_as_smell", source_code
        )
        learner.learn_from_feedback(op2, fb2)
        storage._patterns_cache = None
        matcher.clear_cache()

        # Override must permanently remove the suppression
        assert matcher.is_suppressed_by_ai(fingerprint) is False, (
            "After accepted_as_smell override, issue should no longer be suppressed"
        )

        # --- Step 3: Verify pattern counters are correct ---
        patterns = storage.load_patterns()
        assert len(patterns) == 1
        pattern = list(patterns.values())[0]
        assert pattern.suppressed_count >= 1, "suppressed_count must have been recorded"
        assert pattern.overruled_count > pattern.suppressed_count, (
            "overruled_count must exceed suppressed_count to permanently unblock"
        )

    def test_override_is_permanent_across_multiple_suppression_attempts(
        self, learner, matcher, fingerprinter, sample_issue, source_code, storage
    ):
        """Even if AI suppresses twice, a single override should unlock it permanently."""
        fingerprint = fingerprinter.fingerprint_issue_context(sample_issue, source_code)

        # Two AI suppressions
        for _ in range(2):
            op, fb = _make_operation_and_feedback(
                sample_issue, fingerprint, "suppressed_by_ai", source_code
            )
            learner.learn_from_feedback(op, fb)
            storage._patterns_cache = None

        matcher.clear_cache()
        assert matcher.is_suppressed_by_ai(fingerprint) is True

        # One manual override — this sets overruled_count = suppressed_count + 1
        op_o, fb_o = _make_operation_and_feedback(
            sample_issue, fingerprint, "accepted_as_smell", source_code
        )
        learner.learn_from_feedback(op_o, fb_o)
        storage._patterns_cache = None
        matcher.clear_cache()

        assert matcher.is_suppressed_by_ai(fingerprint) is False, (
            "Manual override must permanently unblock even after multiple suppressions"
        )


class TestCodeSmellAnalyzerIntegration:
    """
    Integration test: CodeSmellAnalyzer should use PatternMatcher before calling
    the LLM orchestrator when AI triage is enabled.
    """

    def test_analyzer_skips_llm_for_cached_suppressed_issue(
        self, storage, fingerprinter, learner, matcher, sample_issue, source_code
    ):
        from refactron.analyzers.code_smell_analyzer import CodeSmellAnalyzer

        # Pre-populate the suppression cache
        fingerprint = fingerprinter.fingerprint_issue_context(sample_issue, source_code)
        op, fb = _make_operation_and_feedback(
            sample_issue, fingerprint, "suppressed_by_ai", source_code
        )
        learner.learn_from_feedback(op, fb)
        matcher.clear_cache()

        # Mock orchestrator — should NOT be called
        mock_orch = MagicMock()
        mock_orch.evaluate_issues_batch.return_value = {}

        config = RefactronConfig()
        config.enable_ai_triage = True
        config.max_parameters = 3  # ensures S001 is triggered

        analyzer = CodeSmellAnalyzer(
            config,
            orchestrator=mock_orch,
            matcher=matcher,
            fingerprinter=fingerprinter,
            learner=learner,
        )

        issues = analyzer.analyze(sample_issue.file_path, source_code)

        # All S001 issues should be suppressed (not returned)
        s001_issues = [i for i in issues if i.rule_id == "S001"]
        assert len(s001_issues) == 0, "Cached-suppressed issues should be filtered out"

        # LLM should NOT have been called since the issue was handled by local cache
        mock_orch.evaluate_issues_batch.assert_not_called()

    def test_analyzer_calls_llm_and_records_suppression_for_new_issue(
        self, storage, fingerprinter, learner, matcher, sample_issue, source_code
    ):
        from refactron.analyzers.code_smell_analyzer import CodeSmellAnalyzer

        # Mock orchestrator returns low confidence → AI suppresses
        mock_orch = MagicMock()
        mock_orch.evaluate_issues_batch.return_value = {
            "S001:1": 0.1  # low confidence
        }

        config = RefactronConfig()
        config.enable_ai_triage = True
        config.include_suppressed = False
        config.max_parameters = 3

        analyzer = CodeSmellAnalyzer(
            config,
            orchestrator=mock_orch,
            matcher=matcher,
            fingerprinter=fingerprinter,
            learner=learner,
        )

        issues = analyzer.analyze(sample_issue.file_path, source_code)

        # LLM should have been called
        mock_orch.evaluate_issues_batch.assert_called_once()

        # After suppression, learner should have persisted a new pattern
        patterns = storage.load_patterns()
        assert len(patterns) >= 1, "Suppression should have created a new pattern"
        any_suppressed = any(p.suppressed_count > 0 for p in patterns.values())
        assert any_suppressed, "At least one pattern must have suppressed_count > 0"

    def test_include_suppressed_flag_shows_cached_issues(
        self, storage, fingerprinter, learner, matcher, sample_issue, source_code
    ):
        from refactron.analyzers.code_smell_analyzer import CodeSmellAnalyzer

        # Pre-populate suppression cache
        fingerprint = fingerprinter.fingerprint_issue_context(sample_issue, source_code)
        op, fb = _make_operation_and_feedback(
            sample_issue, fingerprint, "suppressed_by_ai", source_code
        )
        learner.learn_from_feedback(op, fb)
        matcher.clear_cache()

        config = RefactronConfig()
        config.enable_ai_triage = False  # No LLM needed for this test
        config.include_suppressed = True  # <-- key flag
        config.max_parameters = 3

        analyzer = CodeSmellAnalyzer(
            config,
            orchestrator=None,
            matcher=matcher,
            fingerprinter=fingerprinter,
            learner=learner,
        )

        issues = analyzer.analyze(sample_issue.file_path, source_code)

        suppressed_issues = [i for i in issues if i.metadata.get("suppressed_by_ai") is True]
        assert len(suppressed_issues) >= 1, (
            "--include-suppressed should surface issues that were cached as suppressed"
        )
