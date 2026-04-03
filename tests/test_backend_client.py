"""Tests for BackendLLMClient."""

from unittest.mock import MagicMock, patch

import pytest

from refactron.llm.backend_client import BackendLLMClient


@pytest.fixture
def mock_credentials():
    with patch("refactron.llm.backend_client.load_credentials") as mock:
        creds = MagicMock()
        creds.api_key = "test-api-key"
        creds.access_token = "test-access-token"
        mock.return_value = creds
        yield mock


def test_backend_client_initialization():
    client = BackendLLMClient(backend_url="http://test-backend:3000")
    assert client.backend_url == "http://test-backend:3000"
    assert client.model == "llama-3.3-70b-versatile"


@patch("requests.post")
def test_backend_client_generate(mock_post, mock_credentials):
    # Mock successful response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"content": "Suggested code"}
    mock_post.return_value = mock_response

    client = BackendLLMClient(backend_url="http://test-backend:3000")
    result = client.generate(prompt="Refactor this", system="You are an expert")

    assert result == "Suggested code"

    # Verify request
    mock_post.assert_called_once()
    args, kwargs = mock_post.call_args
    assert args[0] == "http://test-backend:3000/api/llm/generate"
    assert kwargs["json"]["prompt"] == "Refactor this"
    assert kwargs["json"]["system"] == "You are an expert"
    assert kwargs["headers"]["X-API-Key"] == "test-api-key"


@patch("requests.post")
def test_backend_client_error_handling(mock_post, mock_credentials):
    # Mock error response
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error"
    mock_post.return_value = mock_response

    client = BackendLLMClient()
    with pytest.raises(
        RuntimeError, match=r"Backend LLM proxy error \(500\): Internal Server Error"
    ):
        client.generate(prompt="Refactor this")


@patch("requests.get")
def test_backend_client_check_health(mock_get):
    # Mock healthy response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_get.return_value = mock_response

    client = BackendLLMClient()
    assert client.check_health() is True

    # Mock unhealthy response
    mock_response.status_code = 503
    assert client.check_health() is False


# ─────────────── Backend Client (boost) ───────────────


def make_client(creds=None):
    with patch("refactron.llm.backend_client.load_credentials", return_value=creds):
        return BackendLLMClient(backend_url="https://test.api")


class TestBackendClientInit:
    def test_uses_defaults(self):
        client = make_client()
        assert client.backend_url == "https://test.api"
        assert client.model == "llama-3.3-70b-versatile"

    def test_strips_trailing_slash(self):
        with patch("refactron.llm.backend_client.load_credentials", return_value=None):
            client = BackendLLMClient(backend_url="https://api.test/")
        assert not client.backend_url.endswith("/")

    def test_loads_credentials(self):
        creds = MagicMock()
        client = make_client(creds=creds)
        assert client.creds is creds


class TestGenerate:
    def test_success(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"content": "result text"}
        client = make_client()
        with patch("requests.post", return_value=mock_resp):
            result = client.generate("prompt")
        assert result == "result text"

    def test_non_200_raises(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "Internal error"
        mock_resp.headers.get.return_value = None
        client = make_client()
        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="500"):
                client.generate("prompt")

    def test_json_error_in_error_response(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "bad request"
        mock_resp.headers.get.return_value = "application/json"
        mock_resp.json.side_effect = Exception("parse fail")
        client = make_client()
        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(RuntimeError):
                client.generate("prompt")

    def test_json_error_message_extracted(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = "bad"
        mock_resp.headers.get.return_value = "application/json"
        mock_resp.json.return_value = {"error": "invalid key"}
        client = make_client()
        with patch("requests.post", return_value=mock_resp):
            with pytest.raises(RuntimeError, match="invalid key"):
                client.generate("prompt")

    def test_request_exception_wraps(self):
        import requests.exceptions

        client = make_client()
        with patch("requests.post", side_effect=requests.exceptions.ConnectionError("down")):
            with pytest.raises(RuntimeError, match="Failed to connect"):
                client.generate("prompt")

    def test_with_api_key(self):
        creds = MagicMock()
        creds.api_key = "mykey"
        creds.access_token = None
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"content": "ok"}
        client = make_client(creds=creds)
        with patch("requests.post", return_value=mock_resp) as mock_post:
            client.generate("prompt")
        headers = mock_post.call_args[1]["headers"]
        assert headers.get("X-API-Key") == "mykey"

    def test_with_access_token_no_api_key(self):
        creds = MagicMock()
        creds.api_key = None
        creds.access_token = "bearer_token"
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"content": "ok"}
        client = make_client(creds=creds)
        with patch("requests.post", return_value=mock_resp) as mock_post:
            client.generate("prompt")
        headers = mock_post.call_args[1]["headers"]
        assert "Bearer bearer_token" in headers.get("Authorization", "")


class TestCheckHealth:
    def test_healthy(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        client = make_client()
        with patch("requests.get", return_value=mock_resp):
            assert client.check_health() is True

    def test_unhealthy(self):
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        client = make_client()
        with patch("requests.get", return_value=mock_resp):
            assert client.check_health() is False

    def test_exception_returns_false(self):
        import requests.exceptions

        client = make_client()
        with patch("requests.get", side_effect=requests.exceptions.Timeout):
            assert client.check_health() is False
