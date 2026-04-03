"""Tests for CLI login (device-code flow)."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from refactron.cli.auth import auth_status, login, logout, telemetry
from refactron.cli.main import main
from refactron.cli.utils import ApiKeyValidationResult
from refactron.core.credentials import RefactronCredentials
from refactron.core.device_auth import DeviceAuthorization, TokenResponse


def test_login_device_code_flow(monkeypatch, tmp_path: Path) -> None:
    runner = CliRunner()

    # Pretend there are no existing credentials so login flow runs
    import sys

    import refactron.cli.auth
    import refactron.cli.main  # noqa: F401

    monkeypatch.setattr(sys.modules["refactron.cli.main"], "load_credentials", lambda: None)
    monkeypatch.setattr(sys.modules["refactron.cli.auth"], "load_credentials", lambda: None)

    # Stub device authorization response
    def _mock_start_device_authorization(api_base_url: str, timeout_seconds: int = 10):
        assert api_base_url == "http://0.0.0.0:3001"
        return DeviceAuthorization(
            device_code="devcode-123",
            user_code="ABCD-EFGH",
            verification_uri="https://refactron.dev/auth/device",
            expires_in=900,
            interval=1,
        )

    # Stub polling response
    def _mock_poll_for_token(
        device_code: str,
        api_base_url: str,
        interval_seconds: int,
        expires_in_seconds: int,
        timeout_seconds: int = 10,
    ):
        assert device_code == "devcode-123"
        assert api_base_url == "http://0.0.0.0:3001"
        return TokenResponse(
            access_token="jwt.token.here",
            token_type="Bearer",
            expires_in=3600,
            email="user@example.com",
            plan="pro",
            api_key="ref_ABC123",
        )

    saved: dict = {}
    prompts: dict = {}

    def _mock_save_credentials(creds: RefactronCredentials) -> None:
        saved["creds"] = creds

    def _mock_credentials_path() -> Path:
        return tmp_path / "credentials.json"

    def _mock_prompt(text: str, hide_input: bool = False, default: str = "") -> str:
        prompts["text"] = text
        prompts["hide_input"] = hide_input
        return "ref_TESTKEY"

    monkeypatch.setattr(
        "refactron.cli.auth.start_device_authorization", _mock_start_device_authorization
    )
    monkeypatch.setattr("refactron.cli.auth.poll_for_token", _mock_poll_for_token)
    monkeypatch.setattr("refactron.cli.auth.save_credentials", _mock_save_credentials)
    monkeypatch.setattr("refactron.cli.auth.credentials_path", _mock_credentials_path)
    monkeypatch.setattr("refactron.cli.auth.click.prompt", _mock_prompt)
    # API key should be verified before being stored
    monkeypatch.setattr(
        "refactron.cli.auth._validate_api_key",
        lambda *args, **kwargs: ApiKeyValidationResult(ok=True, message="Verified."),
    )

    result = runner.invoke(main, ["login", "--no-browser", "--api-base-url", "http://0.0.0.0:3001"])
    assert result.exit_code == 0, result.output
    assert "Refactron" in result.output
    assert "Login" in result.output
    assert "ABCD-EFGH" in result.output
    assert "app.refactron.dev/login" in result.output
    assert "Login Successful" in result.output
    assert "user@example.com" in result.output
    assert "pro" in result.output

    assert "creds" in saved
    creds: RefactronCredentials = saved["creds"]
    assert creds.api_base_url == "http://0.0.0.0:3001"
    assert creds.access_token == "jwt.token.here"
    # API key should come from user prompt, not from the backend response
    assert creds.api_key == "ref_TESTKEY"


def test_logout_no_credentials(monkeypatch) -> None:
    runner = CliRunner()

    monkeypatch.setattr(sys.modules["refactron.cli.main"], "load_credentials", lambda: None)
    monkeypatch.setattr(sys.modules["refactron.cli.auth"], "load_credentials", lambda: None)
    monkeypatch.setattr("refactron.cli.auth.delete_credentials", lambda path: False)

    result = runner.invoke(main, ["logout"])
    assert result.exit_code == 0
    assert "No credentials found at" in result.output


def test_auth_status_not_logged_in(monkeypatch) -> None:
    runner = CliRunner()

    monkeypatch.setattr(sys.modules["refactron.cli.main"], "load_credentials", lambda: None)
    monkeypatch.setattr(sys.modules["refactron.cli.auth"], "load_credentials", lambda: None)

    result = runner.invoke(main, ["auth", "status"])
    assert result.exit_code == 0
    assert "Not logged in." in result.output


def test_login_skips_when_already_logged_in(monkeypatch, tmp_path: Path) -> None:
    """Login should not start device flow when valid creds exist unless --force is used."""
    runner = CliRunner()

    fake_creds = RefactronCredentials(
        api_base_url="http://0.0.0.0:3001",
        access_token="existing-token",
        token_type="Bearer",
        expires_at=None,
        email="existing@example.com",
        plan="pro",
        api_key="ref_EXISTING",
    )

    # load_credentials returns an existing valid credential

    monkeypatch.setattr(sys.modules["refactron.cli.main"], "load_credentials", lambda: fake_creds)
    monkeypatch.setattr(sys.modules["refactron.cli.auth"], "load_credentials", lambda: fake_creds)

    # Ensure device flow is NOT called
    monkeypatch.setattr(
        "refactron.cli.auth.start_device_authorization",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("should not be called")),
    )

    result = runner.invoke(main, ["login", "--no-browser"])
    assert result.exit_code == 0
    assert "Already authenticated" in result.output
    assert "existing@example.com" in result.output


def test_login_does_not_save_invalid_api_key(monkeypatch, tmp_path: Path) -> None:
    """If API key fails verification, login should abort and not store it."""
    runner = CliRunner()

    monkeypatch.setattr(sys.modules["refactron.cli.main"], "load_credentials", lambda: None)
    monkeypatch.setattr(sys.modules["refactron.cli.auth"], "load_credentials", lambda: None)

    def _mock_start_device_authorization(api_base_url: str, timeout_seconds: int = 10):
        return DeviceAuthorization(
            device_code="devcode-123",
            user_code="ABCD-EFGH",
            verification_uri="https://refactron.dev/auth/device",
            expires_in=900,
            interval=1,
        )

    def _mock_poll_for_token(
        device_code: str,
        api_base_url: str,
        interval_seconds: int,
        expires_in_seconds: int,
        timeout_seconds: int = 10,
    ):
        return TokenResponse(
            access_token="jwt.token.here",
            token_type="Bearer",
            expires_in=3600,
            email="user@example.com",
            plan="pro",
            api_key=None,
        )

    saved: dict = {}

    def _mock_save_credentials(creds: RefactronCredentials) -> None:
        saved["creds"] = creds

    def _mock_credentials_path() -> Path:
        return tmp_path / "credentials.json"

    def _mock_prompt(text: str, hide_input: bool = False, default: str = "") -> str:
        return "ref_INVALID"

    monkeypatch.setattr(
        "refactron.cli.auth.start_device_authorization", _mock_start_device_authorization
    )
    monkeypatch.setattr("refactron.cli.auth.poll_for_token", _mock_poll_for_token)
    monkeypatch.setattr("refactron.cli.auth.save_credentials", _mock_save_credentials)
    monkeypatch.setattr("refactron.cli.auth.credentials_path", _mock_credentials_path)
    monkeypatch.setattr("refactron.cli.auth.click.prompt", _mock_prompt)
    # Simulate backend rejecting the key
    monkeypatch.setattr(
        "refactron.cli.auth._validate_api_key",
        lambda *args, **kwargs: ApiKeyValidationResult(ok=False, message="Invalid API key."),
    )

    result = runner.invoke(main, ["login", "--no-browser"])
    assert result.exit_code != 0
    assert "Invalid API key." in result.output
    # Login should have been aborted before saving any credentials
    assert "creds" not in saved


# ─────────────── Auth (boost) ───────────────


class TestCliAuth:
    @pytest.fixture()
    def runner(self):
        return CliRunner()

    def test_login_already_logged_in_not_expired(self, runner):
        from datetime import datetime, timedelta, timezone

        from refactron.cli.auth import login

        creds = MagicMock()
        creds.access_token = "token"
        creds.email = "user@test.com"
        creds.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        with patch("refactron.cli.auth._setup_logging"), patch(
            "refactron.cli.auth.load_credentials", return_value=creds
        ):
            result = runner.invoke(login, [])
        assert result.exit_code == 0
        assert "Already authenticated" in result.output

    def test_login_force_relogin(self, runner):

        auth_result = MagicMock()
        auth_result.user_code = "CODE123"
        auth_result.device_code = "dev"
        auth_result.interval = 5
        auth_result.expires_in = 300
        token = MagicMock()
        token.access_token = "tok"
        token.token_type = "Bearer"
        token.expires_at.return_value = None
        token.email = "u@test.com"
        token.plan = "free"
        with patch("refactron.cli.auth._setup_logging"), patch(
            "refactron.cli.auth.load_credentials", return_value=None
        ), patch("refactron.cli.auth.start_device_authorization", return_value=auth_result), patch(
            "refactron.cli.auth.poll_for_token", return_value=token
        ), patch(
            "refactron.cli.auth.save_credentials"
        ), patch(
            "refactron.cli.auth.credentials_path", return_value=Path("/tmp/creds.json")
        ), patch(
            "refactron.cli.auth._auth_banner"
        ), patch(
            "webbrowser.open"
        ):
            result = runner.invoke(login, ["--force"])
        assert result.exit_code == 0

    def test_login_start_device_auth_fails(self, runner):

        with patch("refactron.cli.auth._setup_logging"), patch(
            "refactron.cli.auth.load_credentials", return_value=None
        ), patch(
            "refactron.cli.auth.start_device_authorization", side_effect=Exception("conn fail")
        ):
            result = runner.invoke(login, [])
        assert result.exit_code == 1

    def test_login_poll_fails(self, runner):

        auth_result = MagicMock()
        auth_result.user_code = "CODE"
        auth_result.device_code = "dev"
        auth_result.interval = 5
        auth_result.expires_in = 60
        with patch("refactron.cli.auth._setup_logging"), patch(
            "refactron.cli.auth.load_credentials", return_value=None
        ), patch("refactron.cli.auth.start_device_authorization", return_value=auth_result), patch(
            "refactron.cli.auth.poll_for_token", side_effect=Exception("timeout")
        ), patch(
            "webbrowser.open"
        ):
            result = runner.invoke(login, [])
        assert result.exit_code == 1

    def test_logout_success(self, runner):
        from refactron.cli.auth import logout

        with patch("refactron.cli.auth._setup_logging"), patch(
            "refactron.cli.auth.credentials_path", return_value=Path("/tmp/creds.json")
        ), patch("refactron.cli.auth.delete_credentials", return_value=True):
            result = runner.invoke(logout, [])
        assert "Logged Out" in result.output

    def test_logout_no_credentials(self, runner):

        with patch("refactron.cli.auth._setup_logging"), patch(
            "refactron.cli.auth.credentials_path", return_value=Path("/tmp/creds.json")
        ), patch("refactron.cli.auth.delete_credentials", return_value=False):
            result = runner.invoke(logout, [])
        assert "No credentials" in result.output

    def test_auth_status_not_logged_in(self, runner):
        from refactron.cli.auth import auth_status

        with patch("refactron.cli.auth._setup_logging"), patch(
            "refactron.cli.auth.load_credentials", return_value=None
        ):
            result = runner.invoke(auth_status, [])
        assert "Not logged in" in result.output

    def test_auth_status_active(self, runner):

        creds = MagicMock()
        creds.expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        creds.email = "user@test.com"
        creds.plan = "pro"
        creds.api_base_url = "https://api.refactron.dev"
        with patch("refactron.cli.auth._setup_logging"), patch(
            "refactron.cli.auth.load_credentials", return_value=creds
        ), patch("refactron.cli.auth._auth_banner"):
            result = runner.invoke(auth_status, [])
        assert "Active" in result.output

    def test_auth_status_expired(self, runner):

        creds = MagicMock()
        creds.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
        creds.email = "user@test.com"
        creds.plan = "free"
        creds.api_base_url = "https://api.refactron.dev"
        with patch("refactron.cli.auth._setup_logging"), patch(
            "refactron.cli.auth.load_credentials", return_value=creds
        ), patch("refactron.cli.auth._auth_banner"):
            result = runner.invoke(auth_status, [])
        assert "Expired" in result.output

    def test_telemetry_enable(self, runner):
        from refactron.cli.auth import telemetry

        with patch("refactron.cli.auth.enable_telemetry") as mock_enable:
            result = runner.invoke(telemetry, ["--enable"])
        assert result.exit_code == 0
        mock_enable.assert_called_once()

    def test_telemetry_disable(self, runner):

        with patch("refactron.cli.auth.disable_telemetry") as mock_disable:
            result = runner.invoke(telemetry, ["--disable"])
        assert result.exit_code == 0
        mock_disable.assert_called_once()

    def test_telemetry_status_enabled(self, runner):

        mock_collector = MagicMock()
        mock_collector.enabled = True
        with patch("refactron.cli.auth.get_telemetry_collector", return_value=mock_collector):
            result = runner.invoke(telemetry, [])
        assert "Enabled" in result.output

    def test_telemetry_status_disabled(self, runner):

        mock_collector = MagicMock()
        mock_collector.enabled = False
        with patch("refactron.cli.auth.get_telemetry_collector", return_value=mock_collector):
            result = runner.invoke(telemetry, ["--status"])
        assert "Disabled" in result.output
