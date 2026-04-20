"""Pipeline session and timing tracking."""

import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, Optional


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
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert the session to a JSON-serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineSession":
        """Create a session from a dictionary."""
        return cls(**data)
