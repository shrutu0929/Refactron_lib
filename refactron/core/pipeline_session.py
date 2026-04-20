"""Pipeline session and timing tracking."""

import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
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
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """Convert the session to a JSON-serializable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PipelineSession":
        """Create a session from a dictionary."""
        return cls(**data)

    def save(self, directory: Optional[Path] = None) -> Path:
        """
        Persist the session to disk.

        Args:
            directory: Optional directory to save to. Defaults to ~/.refactron/sessions/
        """
        import json
        save_dir = directory or (Path.home() / ".refactron" / "sessions")
        save_dir.mkdir(parents=True, exist_ok=True)

        file_path = save_dir / f"{self.id}.json"
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

        # Also update the 'latest' pointer
        latest_path = save_dir / "latest.json"
        with open(latest_path, "w", encoding="utf-8") as f:
            json.dump({"latest_session_id": self.id}, f)

        return file_path

    @classmethod
    def from_id(
        cls, session_id: str, directory: Optional[Path] = None
    ) -> Optional["PipelineSession"]:
        """Load a session by ID."""
        import json
        save_dir = directory or (Path.home() / ".refactron" / "sessions")
        file_path = save_dir / f"{session_id}.json"

        if not file_path.exists():
            return None

        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return cls.from_dict(data)
