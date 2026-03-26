"""Tests for refactron.cli.repo module."""

import sys
import pytest
from unittest.mock import MagicMock, patch

# Mock torch BEFORE any refactron imports to prevent DLL crash on Windows
mock_torch = MagicMock()
mock_torch.__spec__ = MagicMock()
sys.modules["torch"] = mock_torch

mock_st = MagicMock()
mock_st.__spec__ = MagicMock()
sys.modules["sentence_transformers"] = mock_st

from click.testing import CliRunner
from pathlib import Path

from refactron.core.repositories import Repository
from refactron.core.workspace import WorkspaceMapping


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def mock_repo():
    return Repository(
        id=1,
        name="test-repo",
        full_name="user/test-repo",
        description="A test repository",
        private=False,
        html_url="https://github.com/user/test-repo",
        clone_url="https://github.com/user/test-repo.git",
        ssh_url="git@github.com:user/test-repo.git",
        default_branch="main",
        language="Python",
        updated_at="2023-01-01T00:00:00Z",
    )


@pytest.fixture
def mock_auth_banner():
    """Prevent the auth banner (which may trigger heavy imports) from running."""
    with patch("refactron.cli.repo._auth_banner"):
        yield


def test_repo_list_no_repos(runner, mock_auth_banner):
    """Test 'repo list' when no repositories are returned."""
    with patch("refactron.cli.repo.list_repositories", return_value=[]):
        result = runner.invoke(
            __import__("refactron.cli.repo", fromlist=["repo"]).repo,
            ["list"],
            catch_exceptions=False,
        )
        assert result.exit_code == 0
        assert "No Repositories" in result.output or "No repositories" in result.output


def test_repo_list_with_repos(runner, mock_auth_banner, mock_repo):
    """Test 'repo list' with some repositories."""
    with patch("refactron.cli.repo.list_repositories", return_value=[mock_repo]):
        with patch("refactron.cli.repo.WorkspaceManager.get_workspace", return_value=None):
            result = runner.invoke(
                __import__("refactron.cli.repo", fromlist=["repo"]).repo,
                ["list"],
                catch_exceptions=False,
            )
            assert result.exit_code == 0
            assert "test-repo" in result.output


def test_repo_list_error(runner, mock_auth_banner):
    """Test 'repo list' when the API raises a RuntimeError."""
    with patch(
        "refactron.cli.repo.list_repositories", side_effect=RuntimeError("Not authenticated")
    ):
        result = runner.invoke(
            __import__("refactron.cli.repo", fromlist=["repo"]).repo,
            ["list"],
            catch_exceptions=False,
        )
        assert result.exit_code != 0
        assert "Error" in result.output or "Not authenticated" in result.output


def test_repo_connect_no_args(runner, mock_auth_banner):
    """Test 'repo connect' with no repo name and no path."""
    with patch("refactron.cli.repo.list_repositories", return_value=[]):
        result = runner.invoke(
            __import__("refactron.cli.repo", fromlist=["repo"]).repo,
            ["connect"],
            catch_exceptions=False,
        )
        assert result.exit_code != 0
        assert "Repository name is required" in result.output or result.exit_code == 1


def test_repo_connect_with_path(runner, mock_auth_banner, mock_repo, tmp_path):
    """Test 'repo connect' with existing path."""
    with patch("refactron.cli.repo.list_repositories", return_value=[mock_repo]):
        with patch("refactron.cli.repo.WorkspaceManager.add_workspace") as mock_add:
            with patch("subprocess.Popen"):
                result = runner.invoke(
                    __import__("refactron.cli.repo", fromlist=["repo"]).repo,
                    ["connect", "test-repo", "--path", str(tmp_path)],
                    catch_exceptions=False,
                )
                assert result.exit_code == 0
                assert "Successfully connected" in result.output
                mock_add.assert_called_once()
                mapping = mock_add.call_args[0][0]
                assert mapping.repo_name == "test-repo"
                assert mapping.local_path == str(tmp_path.resolve())


def test_repo_disconnect_not_connected(runner, mock_auth_banner):
    """Test 'repo disconnect' when repo is not connected."""
    with patch("refactron.cli.repo.WorkspaceManager.get_workspace", return_value=None):
        with patch("refactron.cli.repo.WorkspaceManager.get_workspace_by_path", return_value=None):
            result = runner.invoke(
                __import__("refactron.cli.repo", fromlist=["repo"]).repo,
                ["disconnect", "unknown-repo"],
                catch_exceptions=False,
            )
            assert result.exit_code != 0
            assert "is not connected" in result.output


def test_repo_disconnect_success(runner, mock_auth_banner, tmp_path):
    """Test 'repo disconnect' success."""
    mapping = WorkspaceMapping(
        repo_id=1,
        repo_name="test-repo",
        repo_full_name="user/test-repo",
        local_path=str(tmp_path),
        connected_at="2023-01-01T00:00:00Z",
    )
    with patch("refactron.cli.repo.WorkspaceManager.get_workspace", return_value=mapping):
        with patch("refactron.cli.repo.WorkspaceManager.remove_workspace") as mock_remove:
            result = runner.invoke(
                __import__("refactron.cli.repo", fromlist=["repo"]).repo,
                ["disconnect", "test-repo"],
                catch_exceptions=False,
            )
            assert result.exit_code == 0
            assert "Removed workspace mapping" in result.output
            mock_remove.assert_called_once_with("test-repo")
