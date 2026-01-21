"""Tests for Pattern Learning System storage."""

import tempfile
import threading
from pathlib import Path

import pytest

from refactron.patterns.models import (
    PatternMetric,
    ProjectPatternProfile,
    RefactoringFeedback,
    RefactoringPattern,
)
from refactron.patterns.storage import PatternStorage


class TestPatternStorage:
    """Tests for PatternStorage class."""

    @pytest.fixture
    def temp_storage(self) -> PatternStorage:
        """Create a temporary storage instance."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield PatternStorage(storage_dir=Path(tmpdir))

    def test_storage_initialization(self, temp_storage: PatternStorage) -> None:
        """Test storage initialization."""
        assert temp_storage.storage_dir.exists()
        assert temp_storage.patterns_file.exists() is False  # Created on first write
        assert temp_storage.feedback_file.exists() is False

    def test_save_and_load_feedback(self, temp_storage: PatternStorage) -> None:
        """Test saving and loading feedback."""
        feedback = RefactoringFeedback.create(
            operation_id="op-1",
            operation_type="extract_method",
            file_path=Path("test.py"),
            action="accepted",
            code_pattern_hash="hash123",
        )

        temp_storage.save_feedback(feedback)
        feedbacks = temp_storage.load_feedback()

        assert len(feedbacks) == 1
        assert feedbacks[0].operation_id == feedback.operation_id
        assert feedbacks[0].action == feedback.action

    def test_save_and_load_pattern(self, temp_storage: PatternStorage) -> None:
        """Test saving and loading patterns."""
        pattern = RefactoringPattern.create(
            pattern_hash="hash123",
            operation_type="extract_method",
            code_snippet_before="before",
            code_snippet_after="after",
        )

        temp_storage.save_pattern(pattern)
        patterns = temp_storage.load_patterns()

        assert pattern.pattern_id in patterns
        loaded_pattern = patterns[pattern.pattern_id]
        assert loaded_pattern.pattern_hash == pattern.pattern_hash
        assert loaded_pattern.operation_type == pattern.operation_type

    def test_get_pattern(self, temp_storage: PatternStorage) -> None:
        """Test getting a specific pattern."""
        pattern = RefactoringPattern.create(
            pattern_hash="hash123",
            operation_type="extract_method",
            code_snippet_before="before",
            code_snippet_after="after",
        )

        temp_storage.save_pattern(pattern)
        loaded = temp_storage.get_pattern(pattern.pattern_id)

        assert loaded is not None
        assert loaded.pattern_id == pattern.pattern_id

        # Test non-existent pattern
        assert temp_storage.get_pattern("nonexistent") is None

    def test_update_pattern_stats(self, temp_storage: PatternStorage) -> None:
        """Test updating pattern statistics."""
        pattern = RefactoringPattern.create(
            pattern_hash="hash123",
            operation_type="extract_method",
            code_snippet_before="before",
            code_snippet_after="after",
        )
        temp_storage.save_pattern(pattern)

        temp_storage.update_pattern_stats(pattern.pattern_id, "accepted")
        updated_pattern = temp_storage.get_pattern(pattern.pattern_id)

        assert updated_pattern is not None
        assert updated_pattern.accepted_count == 1
        assert updated_pattern.acceptance_rate == 1.0

        temp_storage.update_pattern_stats(pattern.pattern_id, "rejected")
        updated_pattern = temp_storage.get_pattern(pattern.pattern_id)

        assert updated_pattern is not None
        assert updated_pattern.accepted_count == 1
        assert updated_pattern.rejected_count == 1
        assert updated_pattern.acceptance_rate == 0.5

    def test_save_and_load_metrics(self, temp_storage: PatternStorage) -> None:
        """Test saving and loading pattern metrics."""
        metric = PatternMetric(
            pattern_id="pattern-123",
            complexity_reduction=2.5,
            maintainability_improvement=10.0,
        )

        temp_storage.save_pattern_metric(metric)
        metrics = temp_storage.load_pattern_metrics()

        assert metric.pattern_id in metrics
        loaded_metric = metrics[metric.pattern_id]
        assert loaded_metric.complexity_reduction == metric.complexity_reduction

    def test_get_pattern_metric(self, temp_storage: PatternStorage) -> None:
        """Test getting a specific pattern metric."""
        metric = PatternMetric(
            pattern_id="pattern-123",
            complexity_reduction=2.5,
        )

        temp_storage.save_pattern_metric(metric)
        loaded = temp_storage.get_pattern_metric(metric.pattern_id)

        assert loaded is not None
        assert loaded.pattern_id == metric.pattern_id

        # Test non-existent metric
        assert temp_storage.get_pattern_metric("nonexistent") is None

    def test_project_profile_creation(self, temp_storage: PatternStorage) -> None:
        """Test creating and getting project profile."""
        project_path = Path("/test/project")
        profile = temp_storage.get_project_profile(project_path)

        assert profile.project_path == project_path
        assert isinstance(profile.project_id, str)

        # Getting again should return same profile
        profile2 = temp_storage.get_project_profile(project_path)
        assert profile2.project_id == profile.project_id

    def test_save_and_load_project_profile(self, temp_storage: PatternStorage) -> None:
        """Test saving and loading project profiles."""
        profile = ProjectPatternProfile.create(Path("/test/project"))
        profile.enable_pattern("pattern-1")
        profile.set_pattern_weight("pattern-2", 0.8)

        temp_storage.save_project_profile(profile)
        profiles = temp_storage.load_project_profiles()

        assert profile.project_id in profiles
        loaded_profile = profiles[profile.project_id]
        assert loaded_profile.enabled_patterns == profile.enabled_patterns
        assert loaded_profile.pattern_weights == profile.pattern_weights

    def test_feedback_filtering(self, temp_storage: PatternStorage) -> None:
        """Test filtering feedback by pattern_id and project_path."""
        project_path = Path("/test/project")

        feedback1 = RefactoringFeedback.create(
            operation_id="op-1",
            operation_type="extract_method",
            file_path=Path("file1.py"),
            action="accepted",
            code_pattern_hash="hash1",
            project_path=project_path,
        )

        feedback2 = RefactoringFeedback.create(
            operation_id="op-2",
            operation_type="extract_constant",
            file_path=Path("file2.py"),
            action="rejected",
            code_pattern_hash="hash2",
            project_path=project_path,
        )

        feedback3 = RefactoringFeedback.create(
            operation_id="op-3",
            operation_type="extract_method",
            file_path=Path("file3.py"),
            action="accepted",
            code_pattern_hash="hash1",
            project_path=Path("/other/project"),
        )

        temp_storage.save_feedback(feedback1)
        temp_storage.save_feedback(feedback2)
        temp_storage.save_feedback(feedback3)

        # Filter by pattern hash
        filtered = temp_storage.load_feedback(pattern_id="hash1")
        assert len(filtered) == 2
        assert all(f.code_pattern_hash == "hash1" for f in filtered)

        # Filter by project path
        filtered = temp_storage.load_feedback(project_path=project_path)
        assert len(filtered) == 2
        assert all(f.project_path and str(f.project_path) == str(project_path) for f in filtered)

        # Filter by both
        filtered = temp_storage.load_feedback(pattern_id="hash1", project_path=project_path)
        assert len(filtered) == 1
        assert filtered[0].operation_id == "op-1"

    def test_thread_safety(self, temp_storage: PatternStorage) -> None:
        """Test that storage operations are thread-safe."""
        errors = []
        lock = threading.Lock()

        def write_patterns(start: int, count: int) -> None:
            try:
                for i in range(start, start + count):
                    pattern = RefactoringPattern.create(
                        pattern_hash=f"hash{i}",
                        operation_type="extract_method",
                        code_snippet_before=f"before{i}",
                        code_snippet_after=f"after{i}",
                    )
                    temp_storage.save_pattern(pattern)
            except Exception as e:
                with lock:
                    errors.append(e)

        def write_feedback(start: int, count: int) -> None:
            try:
                for i in range(start, start + count):
                    feedback = RefactoringFeedback.create(
                        operation_id=f"op-{i}",
                        operation_type="extract_method",
                        file_path=Path(f"file{i}.py"),
                        action="accepted",
                        code_pattern_hash=f"hash{i}",
                    )
                    temp_storage.save_feedback(feedback)
            except Exception as e:
                with lock:
                    errors.append(e)

        # Create multiple threads writing concurrently
        threads = []
        for i in range(0, 10, 2):
            t1 = threading.Thread(target=write_patterns, args=(i, 2))
            t2 = threading.Thread(target=write_feedback, args=(i, 2))
            threads.extend([t1, t2])
            t1.start()
            t2.start()

        # Wait for all threads to complete
        for t in threads:
            t.join()

        # Check for errors
        assert len(errors) == 0, f"Thread safety errors: {errors}"

        # Verify all data was saved correctly
        patterns = temp_storage.load_patterns()
        feedbacks = temp_storage.load_feedback()

        assert len(patterns) == 10
        assert len(feedbacks) == 10

    def test_cache_clear(self, temp_storage: PatternStorage) -> None:
        """Test clearing in-memory caches."""
        pattern = RefactoringPattern.create(
            pattern_hash="hash123",
            operation_type="extract_method",
            code_snippet_before="before",
            code_snippet_after="after",
        )
        temp_storage.save_pattern(pattern)

        # Load to populate cache
        patterns1 = temp_storage.load_patterns()
        assert len(patterns1) == 1

        # Clear cache and reload
        temp_storage.clear_cache()
        patterns2 = temp_storage.load_patterns()
        assert len(patterns2) == 1

    def test_persistence(self, temp_storage: PatternStorage) -> None:
        """Test that data persists across storage instances."""
        pattern = RefactoringPattern.create(
            pattern_hash="hash123",
            operation_type="extract_method",
            code_snippet_before="before",
            code_snippet_after="after",
        )
        temp_storage.save_pattern(pattern)

        # Create new storage instance pointing to same directory
        storage2 = PatternStorage(storage_dir=temp_storage.storage_dir)
        patterns = storage2.load_patterns()

        assert pattern.pattern_id in patterns
        loaded_pattern = patterns[pattern.pattern_id]
        assert loaded_pattern.pattern_hash == pattern.pattern_hash
