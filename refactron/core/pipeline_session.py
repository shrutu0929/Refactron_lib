"""Pipeline session and timing tracking."""

import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional


@dataclass
class PipelineSession:
    """
    Session container for a pipeline run, including timing metrics for each phase.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    analyze_ms: float = 0.0
    queue_ms: float = 0.0
    apply_ms: float = 0.0
    verify_ms: float = 0.0

    # Application metrics
    files_attempted: int = 0
    files_succeeded: int = 0
    files_failed: int = 0
    blocked_fixes: List[Dict[str, Any]] = field(default_factory=list)
    backup_session_id: Optional[str] = None

    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the session to a JSON-serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineSession":
        """Create a session from a dictionary."""
        return cls(**data)
