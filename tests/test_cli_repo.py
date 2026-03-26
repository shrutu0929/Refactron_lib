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
"""Tests for the refactron repo CLI commands."""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from refactron.cli.repo import repo
from refactron.core.workspace import WorkspaceManager


@pytest.fixture
def runner():
    """Provides a Click CLI runner for testing."""
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
def temp_workspace(tmp_path):
    """Provides an isolated workspace manager for tests."""
    config_path = tmp_path / "workspaces.json"
    mgr = WorkspaceManager(config_path=config_path)
    return mgr


@patch("refactron.cli.repo.WorkspaceManager")
@patch("refactron.cli.repo._spawn_background_indexer")
def test_repo_connect_local_offline(mock_spawn, mock_wsm_cls, runner, tmp_path):
    """Scenario 1 & 2: Inside existing local repo, connects offline instantly."""
    # Setup mock manager
    mock_mgr = MagicMock()
    mock_wsm_cls.return_value = mock_mgr

    # Mock detect_repository to simulate being inside a git repo
    mock_mgr.detect_repository.return_value = "user/my-offline-repo"

    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(repo, ["connect"])

        # Verify it succeeds offline without hitting the API
        assert result.exit_code == 0
        assert "Connected (Local)" in result.output
        assert "detected from .git/config" in result.output
        assert "my-offline-repo" in result.output

        # Verify mapping was added
        mock_mgr.add_workspace.assert_called_once()
        mapping = mock_mgr.add_workspace.call_args[0][0]
        assert mapping.repo_full_name == "user/my-offline-repo"
        assert mapping.repo_name == "my-offline-repo"
        assert mapping.repo_id is None  # Offline = no ID

        # Verify background indexer was spawned
        mock_spawn.assert_called_once()


@patch("refactron.cli.repo.WorkspaceManager")
@patch("refactron.cli.repo.list_repositories")
@patch("refactron.cli.repo.subprocess.run")
@patch("refactron.cli.repo._spawn_background_indexer")
def test_repo_connect_api_fallback(
    mock_spawn, mock_subp_run, mock_list_repos, mock_wsm_cls, runner, tmp_path
):
    """Scenario 3: Outside git repo, repo name provided -> clones via API."""
    mock_mgr = MagicMock()
    mock_wsm_cls.return_value = mock_mgr

    # Simulate being OUTSIDE a git repo
    mock_mgr.detect_repository.return_value = None

    # Simulate API returning repositories
    mock_repo = MagicMock()
    mock_repo.name = "my-online-repo"
    mock_repo.full_name = "user/my-online-repo"
    mock_repo.id = 12345
    mock_repo.clone_url = "https://github.com/user/my-online-repo.git"
    mock_list_repos.return_value = [mock_repo]

    with runner.isolated_filesystem(temp_dir=tmp_path):
        # Pass repo explicit name
        result = runner.invoke(repo, ["connect", "user/my-online-repo"])

        assert result.exit_code == 0
        assert "Connected (API)" in result.output
        assert "cloned from GitHub" in result.output

        # Verify API list was called
        mock_list_repos.assert_called_once()

        # Verify git clone was triggered
        mock_subp_run.assert_called_once()
        assert "git" in mock_subp_run.call_args[0][0]
        assert "clone" in mock_subp_run.call_args[0][0]

        # Verify mapping was added with API ID
        mock_mgr.add_workspace.assert_called_once()
        mapping = mock_mgr.add_workspace.call_args[0][0]
        assert mapping.repo_id == 12345
        assert mapping.repo_name == "my-online-repo"


@patch("refactron.cli.repo.WorkspaceManager")
def test_repo_connect_outside_git_no_args(mock_wsm_cls, runner, tmp_path):
    """If outside git repo and no args provided, it should fail nicely."""
    mock_mgr = MagicMock()
    mock_wsm_cls.return_value = mock_mgr
    mock_mgr.detect_repository.return_value = None

    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(repo, ["connect"])

        assert result.exit_code == 1
        assert "Not a git repository" in result.output
        assert "Usage" in result.output


@patch("refactron.cli.repo.WorkspaceManager")
@patch("refactron.cli.repo.list_repositories")
def test_repo_connect_api_error_fallback(mock_list_repos, mock_wsm_cls, runner, tmp_path):
    """Scenario 4: CI runner (no token, no git context) -> clean error message."""
    mock_mgr = MagicMock()
    mock_wsm_cls.return_value = mock_mgr
    mock_mgr.detect_repository.return_value = None

    # Simulate failure to authenticate to retrieve repositories
    mock_list_repos.side_effect = RuntimeError("Invalid credentials")

    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(repo, ["connect", "some-repo"])

        assert result.exit_code == 1
        assert "Authentication required for cloning" in result.output
        assert "connect offline." in result.output.replace("\n", "")


@patch("refactron.cli.repo.WorkspaceManager")
@patch("refactron.cli.repo.list_repositories")
@patch("refactron.cli.repo.subprocess.run")
@patch("refactron.cli.repo._spawn_background_indexer")
def test_repo_connect_api_fallback_ssh(
    mock_spawn, mock_subp_run, mock_list_repos, mock_wsm_cls, runner, tmp_path
):
    """Scenario 6: Clone using SSH flag."""
    mock_mgr = MagicMock()
    mock_wsm_cls.return_value = mock_mgr
    mock_mgr.detect_repository.return_value = None

    mock_repo = MagicMock()
    mock_repo.name = "my-ssh-repo"
    mock_repo.full_name = "user/my-ssh-repo"
    mock_repo.id = 9999
    mock_repo.clone_url = "https://github.com/user/my-ssh-repo.git"
    mock_repo.ssh_url = "git@github.com:user/my-ssh-repo.git"
    mock_list_repos.return_value = [mock_repo]

    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(repo, ["connect", "--ssh", "user/my-ssh-repo"])

        assert result.exit_code == 0
        assert "Connected (API)" in result.output
        assert "via SSH" in result.output

        mock_subp_run.assert_called_once()
        # Verify it used the ssh_url instead of clone_url
        assert "git@github.com:user/my-ssh-repo.git" in mock_subp_run.call_args[0][0]
