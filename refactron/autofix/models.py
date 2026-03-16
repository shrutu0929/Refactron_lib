"""
Models for auto-fix system.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional


class FixRiskLevel(Enum):
    """Risk levels for automatic fixes."""

    SAFE = 0.0
    LOW = 0.2
    MODERATE = 0.4
    HIGH = 0.6
    VERY_HIGH = 0.8


@dataclass
class FixResult:
    """Result of an automatic fix."""

    success: bool
    reason: str = ""
    diff: Optional[str] = None
    original: Optional[str] = None
    fixed: Optional[str] = None
    risk_score: float = 1.0
    files_affected: List[str] = field(default_factory=list)


@dataclass
class FixStats:
    """Statistics for a batch auto-fix run."""

    total: int = 0
    successful: int = 0
    failed: int = 0
    skipped: int = 0
    files_affected: int = 0
    duration_seconds: float = 0.0

    @property
    def success_rate(self) -> float:
        """Percentage of fixes that succeeded."""
        if self.total == 0:
            return 0.0
        return round(self.successful / self.total * 100, 1)

    def summary(self) -> str:
        """Human-readable summary string."""
        return (
            f"Auto-fix complete: {self.successful}/{self.total} fixes applied "
            f"({self.success_rate}% success rate) | "
            f"Failed: {self.failed} | Skipped: {self.skipped} | "
            f"Files affected: {self.files_affected} | "
            f"Duration: {self.duration_seconds:.2f}s"
        )


@dataclass
class BatchFixReport:
    """Full report for a batch auto-fix run."""

    stats: FixStats = field(default_factory=FixStats)
    results: Dict[int, FixResult] = field(default_factory=dict)
    pending_diffs: List[Dict] = field(default_factory=list)

    def get_successful(self) -> Dict[int, FixResult]:
        """Return only successful fix results."""
        return {k: v for k, v in self.results.items() if v.success}

    def get_failed(self) -> Dict[int, FixResult]:
        """Return only failed fix results."""
        return {k: v for k, v in self.results.items() if not v.success}
