"""Data models for Pattern Learning System."""

import hashlib
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Set


@dataclass
class RefactoringFeedback:
    """Tracks developer acceptance/rejection of refactoring suggestions."""

    operation_id: str
    operation_type: str
    file_path: Path
    timestamp: datetime
    action: str  # "accepted", "rejected", "ignored"
    reason: Optional[str] = None
    code_pattern_hash: Optional[str] = None
    project_path: Optional[Path] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert feedback to dictionary for serialization."""
        data = asdict(self)
        data["file_path"] = str(self.file_path)
        data["timestamp"] = self.timestamp.isoformat()
        if self.project_path:
            data["project_path"] = str(self.project_path)
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RefactoringFeedback":
        """Create feedback from dictionary."""
        data = data.copy()
        data["file_path"] = Path(data["file_path"])
        data["timestamp"] = datetime.fromisoformat(data["timestamp"])
        if "project_path" in data and data["project_path"]:
            data["project_path"] = Path(data["project_path"])
        return cls(**data)

    @classmethod
    def create(
        cls,
        operation_id: str,
        operation_type: str,
        file_path: Path,
        action: str,
        code_pattern_hash: Optional[str] = None,
        project_path: Optional[Path] = None,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "RefactoringFeedback":
        """Create a new feedback record."""
        return cls(
            operation_id=operation_id,
            operation_type=operation_type,
            file_path=file_path,
            timestamp=datetime.now(timezone.utc),
            action=action,
            reason=reason,
            code_pattern_hash=code_pattern_hash,
            project_path=project_path,
            metadata=metadata or {},
        )


@dataclass
class PatternMetric:
    """Metrics for evaluating pattern effectiveness."""

    pattern_id: str
    complexity_reduction: float = 0.0
    maintainability_improvement: float = 0.0
    lines_of_code_change: int = 0
    issue_resolution_count: int = 0
    before_metrics: Dict[str, float] = field(default_factory=dict)
    after_metrics: Dict[str, float] = field(default_factory=dict)
    total_evaluations: int = 0

    def update(
        self,
        complexity_reduction: float,
        maintainability_improvement: float,
        lines_of_code_change: int,
        issue_resolution_count: int,
        before_metrics: Dict[str, float],
        after_metrics: Dict[str, float],
    ) -> "PatternMetric":
        """
        Update metrics with new evaluation data (in-place mutation).

        Returns:
            self to enable method chaining

        Note:
            This method modifies the object in-place. The return value
            is provided to enable method chaining.
        """
        self.total_evaluations += 1
        # Calculate weighted average
        weight = 1.0 / self.total_evaluations
        self.complexity_reduction = (
            1 - weight
        ) * self.complexity_reduction + weight * complexity_reduction
        self.maintainability_improvement = (
            1 - weight
        ) * self.maintainability_improvement + weight * maintainability_improvement
        # Use integer arithmetic with explicit rounding for lines_of_code_change
        self.lines_of_code_change = int(
            round((1 - weight) * self.lines_of_code_change + weight * lines_of_code_change)
        )
        self.issue_resolution_count += issue_resolution_count

        # Merge metrics dictionaries
        for key, value in before_metrics.items():
            if key in self.before_metrics:
                self.before_metrics[key] = (1 - weight) * self.before_metrics[key] + weight * value
            else:
                self.before_metrics[key] = value

        for key, value in after_metrics.items():
            if key in self.after_metrics:
                self.after_metrics[key] = (1 - weight) * self.after_metrics[key] + weight * value
            else:
                self.after_metrics[key] = value

        return self

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for serialization."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PatternMetric":
        """Create metrics from dictionary."""
        return cls(**data)


@dataclass
class RefactoringPattern:
    """Represents a learned pattern from successful refactorings."""

    pattern_id: str
    pattern_hash: str
    operation_type: str
    code_snippet_before: str
    code_snippet_after: str
    acceptance_rate: float = 0.0
    total_occurrences: int = 0
    accepted_count: int = 0
    rejected_count: int = 0
    ignored_count: int = 0
    average_benefit_score: float = 0.0
    first_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_seen: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    project_context: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def update_from_feedback(self, action: str) -> None:
        """Update pattern statistics from feedback."""
        self.total_occurrences += 1
        self.last_seen = datetime.now(timezone.utc)

        if action == "accepted":
            self.accepted_count += 1
        elif action == "rejected":
            self.rejected_count += 1
        elif action == "ignored":
            self.ignored_count += 1

        # Recalculate acceptance rate
        if self.total_occurrences > 0:
            total_decisions = self.accepted_count + self.rejected_count
            if total_decisions > 0:
                self.acceptance_rate = self.accepted_count / total_decisions
            else:
                self.acceptance_rate = 0.0

    def calculate_benefit_score(self, metric: Optional[PatternMetric] = None) -> float:
        """Calculate overall benefit score for this pattern."""
        if metric is None:
            return self.average_benefit_score

        # Combine acceptance rate with metrics
        acceptance_weight = 0.4
        complexity_weight = 0.3
        maintainability_weight = 0.2
        resolution_weight = 0.1

        # Normalize metrics (assume max values)
        normalized_complexity = min(
            abs(metric.complexity_reduction) / 10.0, 1.0
        )  # Assume max 10 reduction
        normalized_maintainability = min(
            metric.maintainability_improvement / 50.0, 1.0
        )  # Assume max 50 improvement
        normalized_resolution = min(metric.issue_resolution_count / 10.0, 1.0)

        score = (
            acceptance_weight * self.acceptance_rate
            + complexity_weight * normalized_complexity
            + maintainability_weight * normalized_maintainability
            + resolution_weight * normalized_resolution
        )

        return score

    def to_dict(self) -> Dict[str, Any]:
        """Convert pattern to dictionary for serialization."""
        data = asdict(self)
        data["first_seen"] = self.first_seen.isoformat()
        data["last_seen"] = self.last_seen.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RefactoringPattern":
        """Create pattern from dictionary."""
        data = data.copy()
        data["first_seen"] = datetime.fromisoformat(data["first_seen"])
        data["last_seen"] = datetime.fromisoformat(data["last_seen"])
        return cls(**data)

    @classmethod
    def create(
        cls,
        pattern_hash: str,
        operation_type: str,
        code_snippet_before: str,
        code_snippet_after: str,
        project_context: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> "RefactoringPattern":
        """Create a new pattern from code snippets."""
        pattern_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        return cls(
            pattern_id=pattern_id,
            pattern_hash=pattern_hash,
            operation_type=operation_type,
            code_snippet_before=code_snippet_before,
            code_snippet_after=code_snippet_after,
            first_seen=now,
            last_seen=now,
            project_context=project_context or {},
            metadata=metadata or {},
        )


@dataclass
class ProjectPatternProfile:
    """Project-specific pattern tuning and rules."""

    project_id: str
    project_path: Path
    enabled_patterns: Set[str] = field(default_factory=set)
    disabled_patterns: Set[str] = field(default_factory=set)
    pattern_weights: Dict[str, float] = field(default_factory=dict)
    rule_thresholds: Dict[str, float] = field(default_factory=dict)
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def generate_project_id(cls, project_path: Path) -> str:
        """Generate a stable project ID from project path."""
        normalized_path = str(project_path.resolve())
        return hashlib.sha256(normalized_path.encode()).hexdigest()[:16]

    @classmethod
    def create(cls, project_path: Path) -> "ProjectPatternProfile":
        """Create a new project profile."""
        project_id = cls.generate_project_id(project_path)
        return cls(
            project_id=project_id,
            project_path=project_path,
            last_updated=datetime.now(timezone.utc),
        )

    def enable_pattern(self, pattern_id: str) -> None:
        """Enable a pattern for this project."""
        self.enabled_patterns.add(pattern_id)
        if pattern_id in self.disabled_patterns:
            self.disabled_patterns.remove(pattern_id)
        self.last_updated = datetime.now(timezone.utc)

    def disable_pattern(self, pattern_id: str) -> None:
        """Disable a pattern for this project."""
        self.disabled_patterns.add(pattern_id)
        if pattern_id in self.enabled_patterns:
            self.enabled_patterns.remove(pattern_id)
        self.last_updated = datetime.now(timezone.utc)

    def set_pattern_weight(self, pattern_id: str, weight: float) -> None:
        """Set custom weight for a pattern."""
        if weight < 0.0 or weight > 1.0:
            raise ValueError(f"Weight must be between 0.0 and 1.0, got {weight}")
        self.pattern_weights[pattern_id] = weight
        self.last_updated = datetime.now(timezone.utc)

    def set_rule_threshold(self, rule_id: str, threshold: float) -> None:
        """Set custom threshold for a rule."""
        self.rule_thresholds[rule_id] = threshold
        self.last_updated = datetime.now(timezone.utc)

    def get_pattern_weight(self, pattern_id: str, default: float = 1.0) -> float:
        """Get weight for a pattern, returning default if not set."""
        return self.pattern_weights.get(pattern_id, default)

    def is_pattern_enabled(self, pattern_id: str) -> bool:
        """Check if a pattern is enabled for this project."""
        if pattern_id in self.disabled_patterns:
            return False
        if self.enabled_patterns:
            return pattern_id in self.enabled_patterns
        return True  # Default to enabled if no restrictions

    def to_dict(self) -> Dict[str, Any]:
        """Convert profile to dictionary for serialization."""
        data = asdict(self)
        data["project_path"] = str(self.project_path)
        data["enabled_patterns"] = list(self.enabled_patterns)
        data["disabled_patterns"] = list(self.disabled_patterns)
        data["last_updated"] = self.last_updated.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProjectPatternProfile":
        """Create profile from dictionary."""
        data = data.copy()
        data["project_path"] = Path(data["project_path"])
        data["enabled_patterns"] = set(data.get("enabled_patterns", []))
        data["disabled_patterns"] = set(data.get("disabled_patterns", []))
        data["last_updated"] = datetime.fromisoformat(data["last_updated"])
        return cls(**data)
