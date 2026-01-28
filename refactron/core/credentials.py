"""Local credential storage for Refactron CLI.

This is intentionally minimal: credentials are stored in a user-only readable file
under ~/.refactron/. For production hardening, an OS keychain integration can be
added later.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional


@dataclass(frozen=True)
class RefactronCredentials:
    """Stored CLI credentials."""

    api_base_url: str
    access_token: str
    token_type: str
    expires_at: Optional[datetime] = None
    email: Optional[str] = None
    plan: Optional[str] = None  # free|pro|enterprise
    api_key: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "api_base_url": self.api_base_url,
            "access_token": self.access_token,
            "token_type": self.token_type,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "email": self.email,
            "plan": self.plan,
            "api_key": self.api_key,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RefactronCredentials":
        expires_at_raw = data.get("expires_at")
        expires_at: Optional[datetime] = None
        if isinstance(expires_at_raw, str) and expires_at_raw.strip():
            expires_at = datetime.fromisoformat(expires_at_raw)
            if expires_at.tzinfo is None:
                expires_at = expires_at.replace(tzinfo=timezone.utc)

        return cls(
            api_base_url=str(data.get("api_base_url") or "").strip(),
            access_token=str(data.get("access_token") or "").strip(),
            token_type=str(data.get("token_type") or "Bearer").strip(),
            expires_at=expires_at,
            email=(str(data["email"]).strip() if data.get("email") else None),
            plan=(str(data["plan"]).strip() if data.get("plan") else None),
            api_key=(str(data["api_key"]).strip() if data.get("api_key") else None),
        )


def credentials_path() -> Path:
    """Default credentials file path."""
    return Path.home() / ".refactron" / "credentials.json"


def save_credentials(creds: RefactronCredentials, path: Optional[Path] = None) -> None:
    """Save credentials to disk (0600 permissions where supported)."""
    target = path or credentials_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(creds.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    # Best-effort permissions tightening (Windows may ignore chmod semantics).
    try:
        os.chmod(target, 0o600)
    except OSError:
        pass


def load_credentials(path: Optional[Path] = None) -> Optional[RefactronCredentials]:
    """Load credentials from disk. Returns None if missing or invalid."""
    target = path or credentials_path()
    if not target.exists():
        return None
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(data, dict):
        return None

    creds = RefactronCredentials.from_dict(data)
    if not creds.api_base_url or not creds.access_token:
        return None
    return creds


def delete_credentials(path: Optional[Path] = None) -> bool:
    """Delete stored credentials. Returns True if deleted, False if not present."""
    target = path or credentials_path()
    try:
        target.unlink()
        return True
    except FileNotFoundError:
        return False
