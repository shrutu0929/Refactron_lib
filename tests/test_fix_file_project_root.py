"""Tests for project_root threading into verification from AutoFixEngine.fix_file().

Covers:
- _discover_project_root() walks up to the nearest VCS/project marker
- _discover_project_root() falls back to the file's directory when no marker exists
- fix_file(verify=True) passes an explicit project_root to VerificationEngine
- fix_file(verify=True) discovers the root when none is supplied,
  instead of always using file_path.parent
"""

from pathlib import Path

from refactron.autofix import engine as engine_module
from refactron.autofix.engine import AutoFixEngine, _discover_project_root
from refactron.core.models import CodeIssue, IssueCategory, IssueLevel


def _trailing_ws_issue(file_path: Path) -> CodeIssue:
    return CodeIssue(
        rule_id="remove_trailing_whitespace",
        message="Trailing whitespace detected",
        file_path=file_path,
        line_number=1,
        category=IssueCategory.STYLE,
        level=IssueLevel.WARNING,
    )


# ─── _discover_project_root ──────────────────────────────────────────────────


def test_discover_project_root_finds_vcs_root(tmp_path):
    """A nested file resolves to the ancestor that holds the .git directory."""
    (tmp_path / ".git").mkdir()
    nested = tmp_path / "services" / "api" / "src"
    nested.mkdir(parents=True)
    file_path = nested / "module.py"
    file_path.write_text("x = 1\n", encoding="utf-8")

    assert _discover_project_root(file_path) == tmp_path


def test_discover_project_root_finds_pyproject(tmp_path):
    """pyproject.toml is treated as a project-root marker."""
    (tmp_path / "pyproject.toml").write_text("[project]\n", encoding="utf-8")
    nested = tmp_path / "pkg"
    nested.mkdir()
    file_path = nested / "module.py"
    file_path.write_text("x = 1\n", encoding="utf-8")

    assert _discover_project_root(file_path) == tmp_path


def test_discover_project_root_falls_back_to_file_dir(tmp_path):
    """With no marker anywhere, the root falls back to the file's own directory."""
    nested = tmp_path / "loose"
    nested.mkdir()
    file_path = nested / "module.py"
    file_path.write_text("x = 1\n", encoding="utf-8")

    assert _discover_project_root(file_path) == nested


# ─── fix_file → VerificationEngine project_root ──────────────────────────────


class _RecordingVerificationEngine:
    """Stand-in that records the project_root it was constructed with."""

    last_project_root = None

    def __init__(self, project_root=None, checks=None):
        type(self).last_project_root = project_root

    def verify(self, original, transformed, file_path):
        # Always allow the transform through so fix_file proceeds normally.
        class _Result:
            safe_to_apply = True
            blocking_reason = None

        return _Result()


def _patch_verification_engine(monkeypatch):
    """Route `from refactron.verification import VerificationEngine` to the recorder."""
    import refactron.verification as verification_pkg

    _RecordingVerificationEngine.last_project_root = None
    monkeypatch.setattr(verification_pkg, "VerificationEngine", _RecordingVerificationEngine)


def test_fix_file_passes_explicit_project_root(tmp_path, monkeypatch):
    """An explicit project_root must reach VerificationEngine unchanged."""
    _patch_verification_engine(monkeypatch)

    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    file_path = nested / "module.py"
    file_path.write_text("x = 1   \n", encoding="utf-8")  # trailing whitespace

    AutoFixEngine().fix_file(
        file_path,
        [_trailing_ws_issue(file_path)],
        dry_run=True,
        verify=True,
        project_root=tmp_path,
    )

    assert _RecordingVerificationEngine.last_project_root == tmp_path


def test_fix_file_discovers_root_when_none_given(tmp_path, monkeypatch):
    """Without an explicit root, fix_file discovers the VCS root, not file_path.parent."""
    _patch_verification_engine(monkeypatch)

    (tmp_path / ".git").mkdir()
    nested = tmp_path / "deep" / "nested"
    nested.mkdir(parents=True)
    file_path = nested / "module.py"
    file_path.write_text("x = 1   \n", encoding="utf-8")  # trailing whitespace

    AutoFixEngine().fix_file(
        file_path,
        [_trailing_ws_issue(file_path)],
        dry_run=True,
        verify=True,
    )

    # The discovered root must be the repo root, not the file's parent directory.
    assert _RecordingVerificationEngine.last_project_root == tmp_path
    assert _RecordingVerificationEngine.last_project_root != file_path.parent


def test_engine_module_exposes_discover_helper():
    """_discover_project_root is importable from the engine module."""
    assert hasattr(engine_module, "_discover_project_root")
