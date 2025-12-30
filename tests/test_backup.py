"""Tests for the backup and rollback system."""

import os
import shutil
import tempfile
from pathlib import Path

import pytest

from refactron.core.backup import BackupManager, BackupRollbackSystem, GitIntegration


class TestBackupManager:
    """Test suite for BackupManager."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        temp = Path(tempfile.mkdtemp())
        yield temp
        if temp.exists():
            shutil.rmtree(temp)

    @pytest.fixture
    def backup_manager(self, temp_dir):
        """Create a BackupManager instance."""
        return BackupManager(root_dir=temp_dir)

    def test_initialization(self, backup_manager, temp_dir):
        """Test BackupManager initializes correctly."""
        assert backup_manager.root_dir == temp_dir
        assert backup_manager.backup_dir == temp_dir / ".refactron-backup"
        assert isinstance(backup_manager._index, dict)

    def test_create_backup_session(self, backup_manager):
        """Test creating a backup session."""
        session_id = backup_manager.create_backup_session("test operation")

        assert session_id.startswith("session_")
        assert len(backup_manager._index["sessions"]) == 1
        assert backup_manager._index["sessions"][0]["description"] == "test operation"

    def test_backup_file(self, backup_manager, temp_dir):
        """Test backing up a single file."""
        test_file = temp_dir / "test.py"
        test_file.write_text("print('hello')")

        session_id = backup_manager.create_backup_session("backup test")
        backup_path = backup_manager.backup_file(test_file, session_id)

        assert backup_path.exists()
        assert backup_path.read_text() == "print('hello')"

    def test_backup_file_not_found(self, backup_manager, temp_dir):
        """Test backing up a nonexistent file raises error."""
        nonexistent = temp_dir / "nonexistent.py"
        session_id = backup_manager.create_backup_session("test")

        with pytest.raises(FileNotFoundError):
            backup_manager.backup_file(nonexistent, session_id)

    def test_backup_multiple_files(self, backup_manager, temp_dir):
        """Test backing up multiple files."""
        file1 = temp_dir / "file1.py"
        file2 = temp_dir / "file2.py"
        file1.write_text("content1")
        file2.write_text("content2")

        session_id = backup_manager.create_backup_session("multi backup")
        backup_paths = backup_manager.backup_files([file1, file2], session_id)

        assert len(backup_paths) == 2
        assert all(p.exists() for p in backup_paths)

    def test_rollback_session(self, backup_manager, temp_dir):
        """Test rolling back a session."""
        test_file = temp_dir / "rollback.py"
        test_file.write_text("original content")

        session_id = backup_manager.create_backup_session("rollback test")
        backup_manager.backup_file(test_file, session_id)

        test_file.write_text("modified content")
        assert test_file.read_text() == "modified content"

        restored_count = backup_manager.rollback_session(session_id)

        assert restored_count == 1
        assert test_file.read_text() == "original content"

    def test_rollback_latest_session(self, backup_manager, temp_dir):
        """Test rolling back the latest session."""
        test_file = temp_dir / "latest.py"
        test_file.write_text("original")

        session_id = backup_manager.create_backup_session("latest test")
        backup_manager.backup_file(test_file, session_id)
        test_file.write_text("modified")

        restored_count = backup_manager.rollback_session()

        assert restored_count == 1
        assert test_file.read_text() == "original"

    def test_rollback_no_sessions(self, backup_manager):
        """Test rollback with no sessions returns 0."""
        restored_count = backup_manager.rollback_session()
        assert restored_count == 0

    def test_list_sessions(self, backup_manager):
        """Test listing backup sessions."""
        backup_manager.create_backup_session("session 1")
        backup_manager.create_backup_session("session 2")

        sessions = backup_manager.list_sessions()

        assert len(sessions) == 2
        assert sessions[0]["description"] == "session 1"
        assert sessions[1]["description"] == "session 2"

    def test_get_session(self, backup_manager):
        """Test getting a specific session."""
        session_id = backup_manager.create_backup_session("specific session")

        session = backup_manager.get_session(session_id)

        assert session is not None
        assert session["id"] == session_id
        assert session["description"] == "specific session"

    def test_get_nonexistent_session(self, backup_manager):
        """Test getting a nonexistent session returns None."""
        session = backup_manager.get_session("nonexistent_session")
        assert session is None

    def test_clear_session(self, backup_manager, temp_dir):
        """Test clearing a specific session."""
        test_file = temp_dir / "clear.py"
        test_file.write_text("content")

        session_id = backup_manager.create_backup_session("clear test")
        backup_manager.backup_file(test_file, session_id)

        assert backup_manager.get_session(session_id) is not None

        result = backup_manager.clear_session(session_id)

        assert result is True
        assert backup_manager.get_session(session_id) is None

    def test_clear_all_sessions(self, backup_manager, temp_dir):
        """Test clearing all sessions."""
        test_file = temp_dir / "clear_all.py"
        test_file.write_text("content")

        session1 = backup_manager.create_backup_session("session 1")
        session2 = backup_manager.create_backup_session("session 2")
        backup_manager.backup_file(test_file, session1)

        count = backup_manager.clear_all_sessions()

        assert count == 2
        assert len(backup_manager.list_sessions()) == 0


class TestGitIntegration:
    """Test suite for GitIntegration."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        temp = Path(tempfile.mkdtemp())
        yield temp
        if temp.exists():
            shutil.rmtree(temp)

    @pytest.fixture
    def git_integration(self, temp_dir):
        """Create a GitIntegration instance."""
        return GitIntegration(repo_path=temp_dir)

    def test_is_git_repo_false(self, git_integration):
        """Test is_git_repo returns False for non-repo."""
        assert git_integration.is_git_repo() is False

    def test_is_git_repo_true(self, temp_dir, git_integration):
        """Test is_git_repo returns True for actual repo."""
        (temp_dir / ".git").mkdir()
        assert git_integration.is_git_repo() is True

    def test_has_uncommitted_changes_no_repo(self, git_integration):
        """Test has_uncommitted_changes returns False for non-repo."""
        assert git_integration.has_uncommitted_changes() is False

    def test_get_current_branch_no_repo(self, git_integration):
        """Test get_current_branch returns None for non-repo."""
        assert git_integration.get_current_branch() is None

    def test_get_current_commit_no_repo(self, git_integration):
        """Test get_current_commit returns None for non-repo."""
        assert git_integration.get_current_commit() is None

    def test_create_pre_refactor_commit_no_repo(self, git_integration):
        """Test create_pre_refactor_commit returns None for non-repo."""
        assert git_integration.create_pre_refactor_commit() is None


class TestBackupRollbackSystem:
    """Test suite for BackupRollbackSystem."""

    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests."""
        temp = Path(tempfile.mkdtemp())
        yield temp
        if temp.exists():
            shutil.rmtree(temp)

    @pytest.fixture
    def system(self, temp_dir):
        """Create a BackupRollbackSystem instance."""
        return BackupRollbackSystem(root_dir=temp_dir)

    def test_initialization(self, system, temp_dir):
        """Test system initializes correctly."""
        assert system.root_dir == temp_dir
        assert system.backup_manager is not None
        assert system.git is not None

    def test_prepare_for_refactoring(self, system, temp_dir):
        """Test preparing for refactoring creates backups."""
        test_file = temp_dir / "prepare.py"
        test_file.write_text("original")

        session_id = system.prepare_for_refactoring(
            files=[test_file],
            description="test refactoring",
            create_git_commit=False,
        )

        assert session_id.startswith("session_")
        session = system.backup_manager.get_session(session_id)
        assert session is not None
        assert len(session["files"]) == 1

    def test_rollback_with_backup(self, system, temp_dir):
        """Test rolling back using file backups."""
        test_file = temp_dir / "rollback.py"
        test_file.write_text("original")

        session_id = system.prepare_for_refactoring(
            files=[test_file],
            description="rollback test",
            create_git_commit=False,
        )

        test_file.write_text("modified")

        result = system.rollback(session_id=session_id, use_git=False)

        assert result["success"] is True
        assert result["files_restored"] == 1
        assert test_file.read_text() == "original"

    def test_rollback_no_sessions(self, system):
        """Test rollback with no sessions."""
        result = system.rollback(use_git=False)

        assert result["success"] is False
        assert "No files to restore" in result["message"]

    def test_list_sessions(self, system, temp_dir):
        """Test listing sessions through the system."""
        test_file = temp_dir / "list.py"
        test_file.write_text("content")

        system.prepare_for_refactoring(
            files=[test_file],
            description="list test",
            create_git_commit=False,
        )

        sessions = system.list_sessions()

        assert len(sessions) == 1
        assert sessions[0]["description"] == "list test"

    def test_clear_all(self, system, temp_dir):
        """Test clearing all sessions."""
        test_file = temp_dir / "clear.py"
        test_file.write_text("content")

        system.prepare_for_refactoring(
            files=[test_file],
            description="clear test",
            create_git_commit=False,
        )

        count = system.clear_all()

        assert count == 1
        assert len(system.list_sessions()) == 0


class TestCLIRollback:
    """Test CLI rollback command."""

    def test_rollback_help(self):
        """Test rollback help command."""
        from click.testing import CliRunner

        from refactron.cli import main

        runner = CliRunner()
        result = runner.invoke(main, ["rollback", "--help"])

        assert result.exit_code == 0
        assert "Rollback refactoring changes" in result.output

    def test_rollback_list_empty(self):
        """Test rollback --list with no sessions."""
        from click.testing import CliRunner

        from refactron.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["rollback", "--list"])

        assert result.exit_code == 0
        assert "No backup sessions found" in result.output

    def test_rollback_no_sessions(self):
        """Test rollback with no sessions."""
        from click.testing import CliRunner

        from refactron.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["rollback"])

        assert result.exit_code == 0
        assert "No backup sessions found" in result.output

    def test_rollback_nonexistent_session(self):
        """Test rollback with nonexistent session."""
        from click.testing import CliRunner

        from refactron.cli import main

        runner = CliRunner()
        with runner.isolated_filesystem():
            result = runner.invoke(main, ["rollback", "--session", "nonexistent"])

        assert result.exit_code == 0
        assert "No backup sessions found" in result.output
