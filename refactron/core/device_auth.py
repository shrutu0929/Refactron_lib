"""Device-code authentication helpers for Refactron CLI.

Implements a minimal Device Authorization Grant-like flow against the Refactron API:
- POST /oauth/device to get (device_code, user_code, verification_uri)
- POST /oauth/token to poll until authorized and receive tokens
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_API_BASE_URL = "https://api.refactron.dev"
DEFAULT_CLIENT_ID = "refactron-cli"


@dataclass(frozen=True)
class DeviceAuthorization:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int


@dataclass(frozen=True)
class TokenResponse:
    access_token: str
    token_type: str
    expires_in: int
    email: Optional[str] = None
    plan: Optional[str] = None
    api_key: Optional[str] = None

    def expires_at(self) -> datetime:
        return datetime.now(timezone.utc) + timedelta(seconds=self.expires_in)


def _normalize_base_url(api_base_url: str) -> str:
    api_base_url = (api_base_url or "").strip()
    return api_base_url[:-1] if api_base_url.endswith("/") else api_base_url


def _post_json(url: str, payload: Dict[str, Any], timeout_seconds: int = 10) -> Dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = Request(
        url=url,
        data=body,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )

    try:
        with urlopen(req, timeout=timeout_seconds) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else {}
    except HTTPError as e:
        # Try to parse JSON error body
        try:
            raw = e.read().decode("utf-8")
            data = json.loads(raw) if raw else {}
            if isinstance(data, dict):
                return data
        except Exception:
            pass
        return {"error": "http_error", "status": e.code}
    except URLError as e:
        return {"error": "network_error", "message": str(e)}


def start_device_authorization(
    api_base_url: str = DEFAULT_API_BASE_URL,
    client_id: str = DEFAULT_CLIENT_ID,
    timeout_seconds: int = 10,
) -> DeviceAuthorization:
    base = _normalize_base_url(api_base_url)
    data = _post_json(
        f"{base}/oauth/device",
        {"client_id": client_id},
        timeout_seconds=timeout_seconds,
    )

    device_code = str(data.get("device_code") or "").strip()
    user_code = str(data.get("user_code") or "").strip()
    verification_uri = str(data.get("verification_uri") or "").strip()
    expires_in_raw = data.get("expires_in", 900)
    interval_raw = data.get("interval", 5)

    if not device_code or not user_code or not verification_uri:
        raise RuntimeError(f"Invalid /oauth/device response: {data}")

    expires_in = int(expires_in_raw) if isinstance(expires_in_raw, (int, float, str)) else 900
    interval = int(interval_raw) if isinstance(interval_raw, (int, float, str)) else 5
    interval = max(1, interval)

    return DeviceAuthorization(
        device_code=device_code,
        user_code=user_code,
        verification_uri=verification_uri,
        expires_in=expires_in,
        interval=interval,
    )


def poll_for_token(
    device_code: str,
    api_base_url: str = DEFAULT_API_BASE_URL,
    client_id: str = DEFAULT_CLIENT_ID,
    interval_seconds: int = 5,
    expires_in_seconds: int = 900,
    timeout_seconds: int = 10,
    sleep_fn: Callable[[float], None] = time.sleep,
) -> TokenResponse:
    base = _normalize_base_url(api_base_url)
    deadline = time.monotonic() + max(1, int(expires_in_seconds))
    interval = max(1, int(interval_seconds))

    while time.monotonic() < deadline:
        data = _post_json(
            f"{base}/oauth/token",
            {
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": device_code,
                "client_id": client_id,
            },
            timeout_seconds=timeout_seconds,
        )

        if not isinstance(data, dict):
            raise RuntimeError(f"Invalid /oauth/token response: {data}")

        err = data.get("error")
        if err == "authorization_pending":
            sleep_fn(interval)
            continue
        if err == "slow_down":
            interval = min(interval + 5, 60)
            sleep_fn(interval)
            continue
        if err == "expired_token":
            raise RuntimeError("Device code expired. Please run 'refactron login' again.")
        if err:
            raise RuntimeError(f"Token polling failed: {data}")

        access_token = str(data.get("access_token") or "").strip()
        token_type = str(data.get("token_type") or "Bearer").strip()
        expires_in = int(data.get("expires_in") or 3600)

        user = data.get("user") or {}
        email = None
        plan = None
        if isinstance(user, dict):
            email = str(user.get("email")).strip() if user.get("email") else None
            plan = str(user.get("plan")).strip() if user.get("plan") else None

        api_key = str(data.get("api_key")).strip() if data.get("api_key") else None

        if not access_token:
            raise RuntimeError(f"Invalid token response: {data}")

        return TokenResponse(
            access_token=access_token,
            token_type=token_type,
            expires_in=expires_in,
            email=email,
            plan=plan,
            api_key=api_key,
        )

    raise RuntimeError("Login timed out waiting for authorization. Please try again.")
