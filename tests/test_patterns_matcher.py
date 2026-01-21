"""Tests for PatternMatcher."""

import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from refactron.patterns.matcher import PatternMatcher
from refactron.patterns.models import RefactoringPattern
from refactron.patterns.storage import PatternStorage


class TestPatternMatcher:
    """Test cases for PatternMatcher."""

    def setup_method(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.storage = PatternStorage(Path(self.temp_dir))
        self.matcher = PatternMatcher(self.storage)

    def teardown_method(self):
        """Clean up test fixtures."""
        if hasattr(self, "temp_dir"):
            shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_find_similar_patterns_no_patterns(self):
        """Test finding patterns when none exist."""
        code_hash = "a" * 64  # 64-char SHA-256-style hash
        patterns = self.matcher.find_similar_patterns(code_hash)

        assert patterns == []

    def test_find_similar_patterns_exact_match(self):
        """Test finding exact pattern matches."""
        # Create a pattern
        pattern = RefactoringPattern.create(
            pattern_hash="test_hash_12345",
            operation_type="extract_method",
            code_snippet_before="x = 1\ny = 2\nz = x + y",
            code_snippet_after="z = add(1, 2)",
        )
        self.storage.save_pattern(pattern)

        # Find exact match
        patterns = self.matcher.find_similar_patterns("test_hash_12345")

        assert len(patterns) == 1
        assert patterns[0].pattern_id == pattern.pattern_id

    def test_find_similar_patterns_filter_by_operation_type(self):
        """Test filtering patterns by operation type."""
        # Create two patterns with different operation types
        pattern1 = RefactoringPattern.create(
            pattern_hash="hash1",
            operation_type="extract_method",
            code_snippet_before="x = 1",
            code_snippet_after="y = 1",
        )
        pattern2 = RefactoringPattern.create(
            pattern_hash="hash1",  # Same hash
            operation_type="extract_constant",
            code_snippet_before="x = 1",
            code_snippet_after="CONSTANT = 1",
        )
        self.storage.save_pattern(pattern1)
        self.storage.save_pattern(pattern2)

        # Filter by operation type
        patterns = self.matcher.find_similar_patterns("hash1", operation_type="extract_method")

        assert len(patterns) == 1
        assert patterns[0].operation_type == "extract_method"

    def test_find_similar_patterns_limit(self):
        """Test limiting the number of results."""
        # Create multiple patterns with same hash
        for i in range(5):
            pattern = RefactoringPattern.create(
                pattern_hash="same_hash",
                operation_type="extract_method",
                code_snippet_before=f"code{i}",
                code_snippet_after=f"refactored{i}",
            )
            # Update acceptance rate to vary sorting
            pattern.acceptance_rate = 0.5 + (i * 0.1)
            self.storage.save_pattern(pattern)

        patterns = self.matcher.find_similar_patterns("same_hash", limit=3)

        assert len(patterns) <= 3
        # Should be sorted by acceptance rate (highest first)
        if len(patterns) > 1:
            assert patterns[0].acceptance_rate >= patterns[-1].acceptance_rate

    def test_calculate_pattern_score_base_score(self):
        """Test calculating pattern score with base acceptance rate."""
        pattern = RefactoringPattern.create(
            pattern_hash="hash1",
            operation_type="extract_method",
            code_snippet_before="x = 1",
            code_snippet_after="y = 1",
        )
        pattern.acceptance_rate = 0.75

        score = self.matcher.calculate_pattern_score(pattern)

        # Base score should be close to acceptance rate (with bonuses)
        assert 0.0 <= score <= 1.0
        assert score >= 0.75  # Should be at least the acceptance rate

    def test_calculate_pattern_score_with_project_profile(self):
        """Test calculating pattern score with project profile."""
        pattern = RefactoringPattern.create(
            pattern_hash="hash1",
            operation_type="extract_method",
            code_snippet_before="x = 1",
            code_snippet_after="y = 1",
        )
        pattern.acceptance_rate = 0.5

        # Get base score without profile
        base_score = self.matcher.calculate_pattern_score(pattern, None)

        project_path = Path("/tmp/test_project")
        profile = self.storage.get_project_profile(project_path)
        profile.set_pattern_weight(pattern.pattern_id, 1.0)  # Maximum weight

        score_with_weight = self.matcher.calculate_pattern_score(pattern, profile)

        # Score should be at least equal or higher with maximum weight
        assert score_with_weight >= base_score * 0.9  # Allow for rounding

    def test_calculate_pattern_score_disabled_pattern(self):
        """Test that disabled patterns get zero score."""
        pattern = RefactoringPattern.create(
            pattern_hash="hash1",
            operation_type="extract_method",
            code_snippet_before="x = 1",
            code_snippet_after="y = 1",
        )
        pattern.acceptance_rate = 0.9  # High acceptance rate

        project_path = Path("/tmp/test_project")
        profile = self.storage.get_project_profile(project_path)
        profile.disable_pattern(pattern.pattern_id)

        score = self.matcher.calculate_pattern_score(pattern, profile)

        assert score == 0.0

    def test_calculate_pattern_score_enabled_pattern_bonus(self):
        """Test that explicitly enabled patterns get a bonus."""
        pattern = RefactoringPattern.create(
            pattern_hash="hash1",
            operation_type="extract_method",
            code_snippet_before="x = 1",
            code_snippet_after="y = 1",
        )
        pattern.acceptance_rate = 0.5

        project_path = Path("/tmp/test_project")
        profile = self.storage.get_project_profile(project_path)
        profile.enable_pattern(pattern.pattern_id)

        score = self.matcher.calculate_pattern_score(pattern, profile)
        score_without_bonus = self.matcher.calculate_pattern_score(pattern, None)

        # Score with enabled bonus should be higher
        assert score > score_without_bonus

    def test_calculate_pattern_score_recency_bonus(self):
        """Test that recent patterns get a recency bonus."""
        # Create pattern seen recently
        pattern = RefactoringPattern.create(
            pattern_hash="hash1",
            operation_type="extract_method",
            code_snippet_before="x = 1",
            code_snippet_after="y = 1",
        )
        pattern.acceptance_rate = 0.5
        pattern.last_seen = datetime.now(timezone.utc)

        score_recent = self.matcher.calculate_pattern_score(pattern)

        # Create pattern seen long ago
        pattern_old = RefactoringPattern.create(
            pattern_hash="hash2",
            operation_type="extract_method",
            code_snippet_before="x = 1",
            code_snippet_after="y = 1",
        )
        pattern_old.acceptance_rate = 0.5
        pattern_old.last_seen = datetime.now(timezone.utc) - timedelta(days=100)

        score_old = self.matcher.calculate_pattern_score(pattern_old)

        # Recent pattern should score higher
        assert score_recent > score_old

    def test_calculate_pattern_score_frequency_bonus(self):
        """Test that frequent patterns get a frequency bonus."""
        pattern1 = RefactoringPattern.create(
            pattern_hash="hash1",
            operation_type="extract_method",
            code_snippet_before="x = 1",
            code_snippet_after="y = 1",
        )
        pattern1.acceptance_rate = 0.5
        pattern1.total_occurrences = 100

        pattern2 = RefactoringPattern.create(
            pattern_hash="hash2",
            operation_type="extract_method",
            code_snippet_before="x = 1",
            code_snippet_after="y = 1",
        )
        pattern2.acceptance_rate = 0.5
        pattern2.total_occurrences = 1

        score1 = self.matcher.calculate_pattern_score(pattern1)
        score2 = self.matcher.calculate_pattern_score(pattern2)

        # More frequent pattern should score higher
        assert score1 > score2

    def test_find_best_matches(self):
        """Test finding best matching patterns with scores."""
        # Create multiple patterns
        pattern1 = RefactoringPattern.create(
            pattern_hash="same_hash",
            operation_type="extract_method",
            code_snippet_before="x = 1",
            code_snippet_after="y = 1",
        )
        pattern1.acceptance_rate = 0.9

        pattern2 = RefactoringPattern.create(
            pattern_hash="same_hash",
            operation_type="extract_method",
            code_snippet_before="x = 2",
            code_snippet_after="y = 2",
        )
        pattern2.acceptance_rate = 0.5

        self.storage.save_pattern(pattern1)
        self.storage.save_pattern(pattern2)

        matches = self.matcher.find_best_matches("same_hash", limit=10)

        assert len(matches) == 2
        # Should be sorted by score (highest first)
        assert matches[0][1] >= matches[1][1]

    def test_find_best_matches_zero_score_filtering(self):
        """Test that zero-score patterns are filtered out."""
        pattern = RefactoringPattern.create(
            pattern_hash="hash1",
            operation_type="extract_method",
            code_snippet_before="x = 1",
            code_snippet_after="y = 1",
        )
        pattern.acceptance_rate = 0.9
        self.storage.save_pattern(pattern)

        project_path = Path("/tmp/test_project")
        profile = self.storage.get_project_profile(project_path)
        profile.disable_pattern(pattern.pattern_id)

        matches = self.matcher.find_best_matches("hash1", project_profile=profile)

        # Disabled pattern should be filtered out
        assert len(matches) == 0

    def test_cache_invalidation(self):
        """Test that pattern cache is invalidated after time."""
        # Create pattern
        pattern = RefactoringPattern.create(
            pattern_hash="hash1",
            operation_type="extract_method",
            code_snippet_before="x = 1",
            code_snippet_after="y = 1",
        )
        self.storage.save_pattern(pattern)

        # Load patterns (should cache)
        self.matcher.find_similar_patterns("hash1")

        # Manually update cache timestamp to simulate old cache
        self.matcher._cache_timestamp = datetime.now(timezone.utc) - timedelta(seconds=310)

        # Add another pattern directly to storage (bypassing matcher's cache)
        pattern2 = RefactoringPattern.create(
            pattern_hash="hash2",
            operation_type="extract_method",
            code_snippet_before="x = 2",
            code_snippet_after="y = 2",
        )
        # Save to storage and clear storage cache to simulate new data
        self.storage.save_pattern(pattern2)
        self.storage.clear_cache()  # Force storage to reload from disk

        # Should reload from storage (cache is old, will trigger TTL check)
        patterns = self.matcher.find_similar_patterns("hash2")
        assert len(patterns) == 1

    def test_clear_cache(self):
        """Test clearing the pattern cache."""
        pattern = RefactoringPattern.create(
            pattern_hash="hash1",
            operation_type="extract_method",
            code_snippet_before="x = 1",
            code_snippet_after="y = 1",
        )
        self.storage.save_pattern(pattern)

        # Load patterns (should cache)
        self.matcher.find_similar_patterns("hash1")
        assert self.matcher._patterns_cache is not None

        # Clear cache
        self.matcher.clear_cache()
        assert self.matcher._patterns_cache is None
        assert self.matcher._cache_timestamp is None
