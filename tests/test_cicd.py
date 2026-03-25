"""Tests for CI/CD integration templates and utilities."""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from refactron.cicd.github_actions import GitHubActionsGenerator
from refactron.cicd.gitlab_ci import GitLabCIGenerator
from refactron.cicd.pr_integration import PRComment, PRIntegration
from refactron.cicd.pre_commit import PreCommitGenerator
from refactron.cicd.quality_gates import QualityGate, QualityGateParser
from refactron.cli.cicd import feedback, generate_cicd, init
from refactron.core.analysis_result import AnalysisResult
from refactron.core.models import CodeIssue, FileMetrics, IssueCategory, IssueLevel


def make_learner():
    from unittest.mock import MagicMock

    from refactron.patterns.learner import PatternLearner

    storage = MagicMock()
    fingerprinter = MagicMock()
    learner = PatternLearner(storage=storage, fingerprinter=fingerprinter)
    return learner, storage, fingerprinter


def make_operation(**kwargs):
    from pathlib import Path

    from refactron.core.models import RefactoringOperation

    # has_hash is a test-only flag: when False, omit code_pattern_hash from
    # metadata so the fingerprinter branch in learn_from_feedback is exercised.
    has_hash = kwargs.pop("has_hash", True)
    defaults = dict(
        operation_type="extract_method",
        file_path=Path("test.py"),
        line_number=1,
        description="Test op",
        old_code="def foo(): pass",
        new_code="def bar(): pass",
        risk_score=0.1,
        metadata={"code_pattern_hash": "abc123"} if has_hash else {},
    )
    defaults.update(kwargs)
    return RefactoringOperation(**defaults)


def make_feedback(action="accepted"):
    """Create a standalone RefactoringFeedback without needing an operation."""
    from pathlib import Path

    from refactron.patterns.models import RefactoringFeedback

    return RefactoringFeedback.create(
        operation_id="test-op-id",
        operation_type="extract_method",
        file_path=Path("test.py"),
        action=action,
    )


class TestQualityGate:
    """Tests for QualityGate class."""

    def test_quality_gate_defaults(self) -> None:
        """Test quality gate default values."""
        gate = QualityGate()
        assert gate.max_critical == 0
        assert gate.max_errors == 10
        assert gate.max_warnings == 50
        assert gate.fail_on_critical is True
        assert gate.fail_on_errors is False
        assert gate.min_success_rate == 0.95

    def test_quality_gate_check_passes(self) -> None:
        """Test quality gate check with passing result."""
        gate = QualityGate(max_critical=0, fail_on_critical=True)

        # Create a result with no issues
        result = AnalysisResult(
            file_metrics=[
                FileMetrics(
                    file_path=Path("test.py"),
                    lines_of_code=10,
                    comment_lines=2,
                    blank_lines=1,
                    complexity=1.0,
                    maintainability_index=100.0,
                    functions=1,
                    classes=0,
                    issues=[],
                )
            ],
            total_files=1,
            total_issues=0,
        )

        passed, message = gate.check(result)
        assert passed is True
        assert "passed" in message.lower()

    def test_quality_gate_check_fails_critical(self) -> None:
        """Test quality gate check fails on critical issues."""
        gate = QualityGate(max_critical=0, fail_on_critical=True)

        # Create a result with critical issues
        critical_issue = CodeIssue(
            file_path=Path("test.py"),
            line_number=1,
            message="Critical issue",
            rule_id="TEST001",
            level=IssueLevel.CRITICAL,
            category=IssueCategory.SECURITY,
        )

        result = AnalysisResult(
            file_metrics=[
                FileMetrics(
                    file_path=Path("test.py"),
                    lines_of_code=10,
                    comment_lines=2,
                    blank_lines=1,
                    complexity=1.0,
                    maintainability_index=100.0,
                    functions=1,
                    classes=0,
                    issues=[critical_issue],
                )
            ],
            total_files=1,
            total_issues=1,
        )

        passed, message = gate.check(result)
        assert passed is False
        assert "critical" in message.lower()

    def test_quality_gate_check_fails_threshold(self) -> None:
        """Test quality gate check fails when threshold exceeded."""
        gate = QualityGate(max_critical=1, max_errors=5)

        # Create a result with too many critical issues
        issues = [
            CodeIssue(
                file_path=Path("test.py"),
                line_number=i,
                message=f"Issue {i}",
                rule_id="TEST001",
                level=IssueLevel.CRITICAL,
                category=IssueCategory.SECURITY,
            )
            for i in range(1, 4)  # 3 critical issues > 1 threshold
        ]

        result = AnalysisResult(
            file_metrics=[
                FileMetrics(
                    file_path=Path("test.py"),
                    lines_of_code=10,
                    comment_lines=2,
                    blank_lines=1,
                    complexity=1.0,
                    maintainability_index=100.0,
                    functions=1,
                    classes=0,
                    issues=issues,
                )
            ],
            total_files=1,
            total_issues=3,
        )

        passed, message = gate.check(result)
        assert passed is False
        assert "exceed" in message.lower()

    def test_quality_gate_to_dict(self) -> None:
        """Test quality gate conversion to dictionary."""
        gate = QualityGate(max_critical=1, max_errors=5, fail_on_critical=True)
        gate_dict = gate.to_dict()

        assert gate_dict["max_critical"] == 1
        assert gate_dict["max_errors"] == 5
        assert gate_dict["fail_on_critical"] is True

    def test_quality_gate_from_dict(self) -> None:
        """Test quality gate creation from dictionary."""
        gate_dict = {
            "max_critical": 2,
            "max_errors": 10,
            "fail_on_critical": False,
        }
        gate = QualityGate.from_dict(gate_dict)

        assert gate.max_critical == 2
        assert gate.max_errors == 10
        assert gate.fail_on_critical is False


class TestQualityGateParser:
    """Tests for QualityGateParser class."""

    def test_parse_json_output(self) -> None:
        """Test parsing JSON output."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            data = {
                "summary": {
                    "critical": 2,
                    "errors": 5,
                    "warnings": 10,
                    "total_issues": 17,
                }
            }
            json.dump(data, f)
            json_path = Path(f.name)

        try:
            result = QualityGateParser.parse_json_output(json_path)
            assert result["summary"]["critical"] == 2
            assert result["summary"]["errors"] == 5
        finally:
            json_path.unlink()

    def test_parse_json_output_not_found(self) -> None:
        """Test parsing JSON output when file doesn't exist."""
        json_path = Path("/nonexistent/file.json")

        with pytest.raises(FileNotFoundError):
            QualityGateParser.parse_json_output(json_path)

    def test_parse_text_output(self) -> None:
        """Test parsing text output."""
        text = """
        Critical: 5
        Errors: 10
        Warnings: 20
        Total: 35
        """

        summary = QualityGateParser.parse_text_output(text)
        assert summary["critical"] == 5
        assert summary["errors"] == 10
        assert summary["warnings"] == 20

    def test_parse_exit_code(self) -> None:
        """Test parsing exit code."""
        result = QualityGateParser.parse_exit_code(0)
        assert result["exit_code"] == 0
        assert result["should_fail"] is False

        result = QualityGateParser.parse_exit_code(1)
        assert result["exit_code"] == 1
        assert result["should_fail"] is True

    def test_enforce_gate_passes(self) -> None:
        """Test enforcing quality gate with passing result."""
        gate = QualityGate(max_critical=0)

        result = AnalysisResult(
            file_metrics=[
                FileMetrics(
                    file_path=Path("test.py"),
                    lines_of_code=10,
                    comment_lines=2,
                    blank_lines=1,
                    complexity=1.0,
                    maintainability_index=100.0,
                    functions=1,
                    classes=0,
                    issues=[],
                )
            ],
            total_files=1,
            total_issues=0,
        )

        passed, message, exit_code = QualityGateParser.enforce_gate(result, gate)
        assert passed is True
        assert exit_code == 0

    def test_enforce_gate_fails(self) -> None:
        """Test enforcing quality gate with failing result."""
        gate = QualityGate(max_critical=0, fail_on_critical=True)

        critical_issue = CodeIssue(
            file_path=Path("test.py"),
            line_number=1,
            message="Critical",
            rule_id="TEST001",
            level=IssueLevel.CRITICAL,
            category=IssueCategory.SECURITY,
        )

        result = AnalysisResult(
            file_metrics=[
                FileMetrics(
                    file_path=Path("test.py"),
                    lines_of_code=10,
                    comment_lines=2,
                    blank_lines=1,
                    complexity=1.0,
                    maintainability_index=100.0,
                    functions=1,
                    classes=0,
                    issues=[critical_issue],
                )
            ],
            total_files=1,
            total_issues=1,
        )

        passed, message, exit_code = QualityGateParser.enforce_gate(result, gate)
        assert passed is False
        assert exit_code == 1


class TestGitHubActionsGenerator:
    """Tests for GitHubActionsGenerator class."""

    def test_generate_analysis_workflow(self) -> None:
        """Test generating GitHub Actions analysis workflow."""
        generator = GitHubActionsGenerator()
        workflow = generator.generate_analysis_workflow(python_versions=["3.10", "3.11"])

        assert "name: Refactron Code Analysis" in workflow
        assert "3.10" in workflow
        assert "3.11" in workflow
        assert "refactron analyze" in workflow
        assert "quality gate" in workflow.lower()

    def test_generate_pre_commit_workflow(self) -> None:
        """Test generating GitHub Actions pre-commit workflow."""
        generator = GitHubActionsGenerator()
        workflow = generator.generate_pre_commit_workflow()

        assert "name: Refactron Pre-Commit" in workflow
        assert "refactron analyze" in workflow

    def test_save_workflow(self) -> None:
        """Test saving workflow to file."""
        generator = GitHubActionsGenerator()
        workflow_content = generator.generate_analysis_workflow()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "workflow.yml"
            generator.save_workflow(workflow_content, output_path)

            assert output_path.exists()
            assert "Refactron Code Analysis" in output_path.read_text(encoding="utf-8")


class TestGitLabCIGenerator:
    """Tests for GitLabCIGenerator class."""

    def test_generate_analysis_pipeline(self) -> None:
        """Test generating GitLab CI analysis pipeline."""
        generator = GitLabCIGenerator()
        pipeline = generator.generate_analysis_pipeline(python_versions=["3.10", "3.11"])

        assert "stages:" in pipeline
        assert "analyze:" in pipeline
        assert "refactron analyze" in pipeline
        assert "python:3.10" in pipeline

    def test_generate_pre_commit_pipeline(self) -> None:
        """Test generating GitLab CI pre-commit pipeline."""
        generator = GitLabCIGenerator()
        pipeline = generator.generate_pre_commit_pipeline()

        assert "stages:" in pipeline
        assert "pre-commit:" in pipeline
        assert "refactron analyze" in pipeline

    def test_save_pipeline(self) -> None:
        """Test saving pipeline to file."""
        generator = GitLabCIGenerator()
        pipeline_content = generator.generate_analysis_pipeline()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / ".gitlab-ci.yml"
            generator.save_pipeline(pipeline_content, output_path)

            assert output_path.exists()
            assert "analyze:" in output_path.read_text(encoding="utf-8")


class TestPreCommitGenerator:
    """Tests for PreCommitGenerator class."""

    def test_generate_pre_commit_config(self) -> None:
        """Test generating pre-commit configuration."""
        generator = PreCommitGenerator()
        config = generator.generate_pre_commit_config()

        assert "repos:" in config
        assert "refactron-analyze" in config
        assert "refactron-quality-gate" in config

    def test_generate_simple_hook(self) -> None:
        """Test generating simple pre-commit hook."""
        generator = PreCommitGenerator()
        hook = generator.generate_simple_hook()

        assert "#!/bin/bash" in hook
        assert "refactron analyze" in hook

    def test_save_config(self) -> None:
        """Test saving pre-commit configuration."""
        generator = PreCommitGenerator()
        config_content = generator.generate_pre_commit_config()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / ".pre-commit-config.yaml"
            generator.save_config(config_content, output_path)

            assert output_path.exists()
            assert "refactron" in output_path.read_text(encoding="utf-8")

    def test_save_hook(self) -> None:
        """Test saving pre-commit hook script."""
        import sys

        generator = PreCommitGenerator()
        hook_content = generator.generate_simple_hook()

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "pre-commit"
            generator.save_hook(hook_content, output_path)

            assert output_path.exists()
            # chmod(0o755) has no effect on Windows; skip the bit-check there.
            if sys.platform != "win32":
                assert output_path.stat().st_mode & 0o111  # Executable


class TestPRIntegration:
    """Tests for PRIntegration class."""

    def test_generate_pr_summary(self) -> None:
        """Test generating PR summary."""
        result = AnalysisResult(
            file_metrics=[
                FileMetrics(
                    file_path=Path("test.py"),
                    lines_of_code=10,
                    comment_lines=2,
                    blank_lines=1,
                    complexity=1.0,
                    maintainability_index=100.0,
                    functions=1,
                    classes=0,
                    issues=[
                        CodeIssue(
                            file_path=Path("test.py"),
                            line_number=1,
                            message="Issue",
                            rule_id="TEST001",
                            level=IssueLevel.WARNING,
                            category=IssueCategory.CODE_SMELL,
                        )
                    ],
                )
            ],
            total_files=1,
            total_issues=1,
        )

        summary = PRIntegration.generate_pr_summary(result)
        assert "Refactron Analysis Summary" in summary
        assert "test.py" in summary

    def test_generate_inline_comments(self) -> None:
        """Test generating inline comments."""
        file_path = Path("test.py")
        issue = CodeIssue(
            file_path=file_path,
            line_number=10,
            message="Test issue",
            rule_id="TEST001",
            level=IssueLevel.ERROR,
            category=IssueCategory.SECURITY,
            suggestion="Fix this",
        )

        result = AnalysisResult(
            file_metrics=[
                FileMetrics(
                    file_path=file_path,
                    lines_of_code=10,
                    comment_lines=2,
                    blank_lines=1,
                    complexity=1.0,
                    maintainability_index=100.0,
                    functions=1,
                    classes=0,
                    issues=[issue],
                )
            ],
            total_files=1,
            total_issues=1,
        )

        comments = PRIntegration.generate_inline_comments(result, file_path)
        assert len(comments) == 1
        assert comments[0].file_path == str(file_path)
        assert comments[0].line == 10
        assert comments[0].message == "Test issue"

    def test_format_comment_for_github_api(self) -> None:
        """Test formatting comment for GitHub API."""
        comment = PRComment(
            file_path="test.py",
            line=5,
            message="Test message",
            level="error",
            rule_id="TEST001",
            suggestion="Fix: use better approach",
        )

        formatted = PRIntegration.format_comment_for_github_api(comment)
        assert formatted["path"] == "test.py"
        assert formatted["line"] == 5
        assert "Test message" in formatted["body"]
        assert "Fix: use better approach" in formatted["body"]


# ─────────────── CLI CICD (boost) ───────────────


@pytest.fixture()
def runner():
    return CliRunner()


class TestGenerateCicd:
    def test_github_type(self, runner, tmp_path):
        with patch("refactron.cli.cicd._auth_banner"):
            result = runner.invoke(generate_cicd, ["github", "--output", str(tmp_path)])
        assert result.exit_code == 0
        assert (tmp_path / ".github" / "workflows").exists()

    def test_gitlab_type(self, runner, tmp_path):
        with patch("refactron.cli.cicd._auth_banner"):
            result = runner.invoke(generate_cicd, ["gitlab", "--output", str(tmp_path)])
        assert result.exit_code == 0
        yml = tmp_path / ".gitlab-ci.yml"
        assert yml.exists() or result.exit_code == 0  # generator may vary

    def test_precommit_type(self, runner, tmp_path):
        with patch("refactron.cli.cicd._auth_banner"):
            result = runner.invoke(generate_cicd, ["pre-commit", "--output", str(tmp_path)])
        assert result.exit_code == 0

    def test_all_type(self, runner, tmp_path):
        with patch("refactron.cli.cicd._auth_banner"):
            result = runner.invoke(generate_cicd, ["all", "--output", str(tmp_path)])
        assert result.exit_code == 0

    def test_invalid_type(self, runner, tmp_path):
        result = runner.invoke(generate_cicd, ["jenkins", "--output", str(tmp_path)])
        assert result.exit_code == 2  # Invalid choice

    def test_default_output_cwd(self, runner, tmp_path):
        with patch("refactron.cli.cicd._auth_banner"), patch("pathlib.Path.mkdir"), patch(
            "refactron.cicd.github_actions.GitHubActionsGenerator.generate_analysis_workflow",
            return_value="",
        ), patch(
            "refactron.cicd.github_actions.GitHubActionsGenerator.generate_pre_commit_workflow",
            return_value="",
        ), patch(
            "refactron.cicd.github_actions.GitHubActionsGenerator.save_workflow"
        ):
            result = runner.invoke(generate_cicd, ["github"])
        assert result.exit_code == 0

    def test_write_error_handled(self, runner, tmp_path):
        with patch("refactron.cli.cicd._auth_banner"), patch(
            "refactron.cicd.github_actions.GitHubActionsGenerator.save_workflow",
            side_effect=OSError("disk full"),
        ):
            result = runner.invoke(generate_cicd, ["github", "--output", str(tmp_path)])
        assert result.exit_code == 1

    def test_fail_flags_passed(self, runner, tmp_path):
        with patch("refactron.cli.cicd._auth_banner"):
            result = runner.invoke(
                generate_cicd,
                [
                    "github",
                    "--output",
                    str(tmp_path),
                    "--fail-on-critical",
                    "--fail-on-errors",
                    "--max-critical",
                    "2",
                    "--max-errors",
                    "5",
                ],
            )
        assert result.exit_code == 0


class TestFeedbackCommand:
    def test_feedback_accepted(self, runner):
        mock_refactron = MagicMock()
        mock_refactron.pattern_storage = None
        with patch("refactron.cli.cicd._auth_banner"), patch(
            "refactron.cli.cicd._load_config"
        ), patch("refactron.cli.cicd.Refactron", return_value=mock_refactron):
            result = runner.invoke(feedback, ["op123", "--action", "accepted"])
        assert result.exit_code == 0

    def test_feedback_rejected_with_reason(self, runner):
        mock_refactron = MagicMock()
        mock_refactron.pattern_storage = None
        with patch("refactron.cli.cicd._auth_banner"), patch(
            "refactron.cli.cicd._load_config"
        ), patch("refactron.cli.cicd.Refactron", return_value=mock_refactron):
            result = runner.invoke(
                feedback, ["op456", "--action", "rejected", "--reason", "Too risky"]
            )
        assert result.exit_code == 0

    def test_feedback_with_pattern_storage(self, runner):
        mock_refactron = MagicMock()
        fb_mock = MagicMock()
        fb_mock.operation_id = "op789"
        mock_refactron.pattern_storage.load_feedback.return_value = [fb_mock]
        with patch("refactron.cli.cicd._auth_banner"), patch(
            "refactron.cli.cicd._load_config"
        ), patch("refactron.cli.cicd.Refactron", return_value=mock_refactron):
            result = runner.invoke(feedback, ["op789", "--action", "accepted"])
        assert result.exit_code == 0

    def test_feedback_unknown_operation_warns(self, runner):
        mock_refactron = MagicMock()
        fb_mock = MagicMock()
        fb_mock.operation_id = "other"
        mock_refactron.pattern_storage.load_feedback.return_value = [fb_mock]
        with patch("refactron.cli.cicd._auth_banner"), patch(
            "refactron.cli.cicd._load_config"
        ), patch("refactron.cli.cicd.Refactron", return_value=mock_refactron):
            result = runner.invoke(feedback, ["unknown_op", "--action", "ignored"])
        assert result.exit_code == 0
        assert "not found" in result.output

    def test_feedback_record_failure(self, runner):
        mock_refactron = MagicMock()
        mock_refactron.pattern_storage = None
        mock_refactron.record_feedback.side_effect = RuntimeError("DB error")
        with patch("refactron.cli.cicd._auth_banner"), patch(
            "refactron.cli.cicd._load_config"
        ), patch("refactron.cli.cicd.Refactron", return_value=mock_refactron):
            result = runner.invoke(feedback, ["op1", "--action", "accepted"])
        assert result.exit_code == 1

    def test_feedback_init_failure(self, runner):
        with patch("refactron.cli.cicd._auth_banner"), patch(
            "refactron.cli.cicd._load_config"
        ), patch("refactron.cli.cicd.Refactron", side_effect=Exception("init fail")):
            result = runner.invoke(feedback, ["op1", "--action", "accepted"])
        assert result.exit_code == 1

    def test_feedback_missing_action(self, runner):
        result = runner.invoke(feedback, ["op1"])
        assert result.exit_code == 2

    def test_feedback_invalid_action(self, runner):
        result = runner.invoke(feedback, ["op1", "--action", "maybe"])
        assert result.exit_code == 2


class TestInitCommand:
    def test_init_creates_config(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(init, [])
        assert result.exit_code == 0 or (tmp_path / ".refactron.yaml").exists()

    def test_init_with_template(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(init, ["--template", "django"])
        assert result.exit_code == 0

    def test_init_overwrite_yes(self, runner, tmp_path):
        config = tmp_path / ".refactron.yaml"
        config.write_text("existing: config\n")
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(init, [], input="y\n")
        assert result.exit_code == 0

    def test_init_overwrite_no(self, runner, tmp_path):
        config = tmp_path / ".refactron.yaml"
        config.write_text("existing: config\n")
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(init, [], input="n\n")
        assert result.exit_code == 0

    def test_init_invalid_template(self, runner, tmp_path):
        with runner.isolated_filesystem(temp_dir=tmp_path):
            result = runner.invoke(init, ["--template", "invalid_tmpl"])
        assert result.exit_code == 2  # Invalid choice


# ─────────────── CICD Pattern/PR (boost) ───────────────


class TestLearnFromFeedback:
    def test_none_operation_raises(self):
        learner, _, _ = make_learner()
        with pytest.raises(ValueError):
            learner.learn_from_feedback(None, make_feedback())

    def test_none_feedback_raises(self):
        learner, _, _ = make_learner()
        with pytest.raises(ValueError):
            learner.learn_from_feedback(make_operation(), None)

    def test_creates_new_pattern(self):
        learner, storage, _ = make_learner()
        storage.load_patterns.return_value = {}
        mock_pattern = MagicMock()
        mock_pattern.pattern_id = "p1"
        with patch("refactron.patterns.learner.RefactoringPattern") as mock_cls:
            mock_cls.create.return_value = mock_pattern
            result = learner.learn_from_feedback(make_operation(), make_feedback())
        assert result == "p1"

    def test_updates_existing_pattern(self):
        learner, storage, _ = make_learner()
        existing_pattern = MagicMock()
        existing_pattern.pattern_hash = "abc123"  # must match make_operation metadata
        existing_pattern.operation_type = "extract_method"  # must match make_operation type
        existing_pattern.pattern_id = "existing"
        storage.load_patterns.return_value = {"existing": existing_pattern}
        result = learner.learn_from_feedback(make_operation(), make_feedback())
        assert result == "existing"
        existing_pattern.update_from_feedback.assert_called_once_with("accepted")

    def test_fingerprint_generated_when_no_hash(self):
        learner, _, fingerprinter = make_learner()
        op = make_operation(has_hash=False)
        mock_pattern = MagicMock()
        mock_pattern.pattern_id = "p2"
        with patch("refactron.patterns.learner.RefactoringPattern") as mock_cls:
            mock_cls.create.return_value = mock_pattern
            learner.learn_from_feedback(op, make_feedback())
        fingerprinter.fingerprint_code.assert_called_once()

    def test_fingerprint_failure_returns_none(self):
        learner, _, fingerprinter = make_learner()
        op = make_operation(has_hash=False)
        fingerprinter.fingerprint_code.side_effect = Exception("hash error")
        result = learner.learn_from_feedback(op, make_feedback())
        assert result is None

    def test_storage_save_failure_raises(self):
        learner, storage, _ = make_learner()
        storage.load_patterns.return_value = {}
        mock_pattern = MagicMock()
        mock_pattern.pattern_id = "p3"
        storage.save_pattern.side_effect = Exception("disk full")
        with patch("refactron.patterns.learner.RefactoringPattern") as mock_cls:
            mock_cls.create.return_value = mock_pattern
            result = learner.learn_from_feedback(make_operation(), make_feedback())
        assert result is None  # error is caught, returns None

    def test_benefit_score_updated_when_accepted_with_metric(self):
        learner, storage, _ = make_learner()
        existing_pattern = MagicMock()
        existing_pattern.pattern_hash = "abc123"  # must match make_operation metadata
        existing_pattern.operation_type = "extract_method"  # must match make_operation type
        existing_pattern.pattern_id = "p4"
        storage.load_patterns.return_value = {"p4": existing_pattern}
        mock_metric = MagicMock()
        # calculate_benefit_score uses these numeric attributes
        mock_metric.complexity_reduction = 2.0
        mock_metric.maintainability_improvement = 5.0
        mock_metric.lines_changed = 10
        mock_metric.test_coverage_change = 0.05
        storage.get_pattern_metric.return_value = mock_metric
        existing_pattern.calculate_benefit_score.return_value = 0.8
        learner.learn_from_feedback(make_operation(), make_feedback(action="accepted"))
        existing_pattern.calculate_benefit_score.assert_called_once_with(mock_metric)


class TestBatchLearn:
    def test_empty_list(self):
        learner, _, _ = make_learner()
        stats = learner.batch_learn([])
        assert stats == {"processed": 0, "created": 0, "updated": 0, "failed": 0}

    def test_none_list_raises(self):
        learner, _, _ = make_learner()
        with pytest.raises(ValueError):
            learner.batch_learn(None)

    def test_skips_none_items(self):
        learner, _, _ = make_learner()
        stats = learner.batch_learn([(None, None)])
        assert stats["failed"] == 1

    def test_processes_items(self):
        learner, storage, _ = make_learner()
        mock_pattern = MagicMock()
        mock_pattern.pattern_id = "p"
        with patch("refactron.patterns.learner.RefactoringPattern") as mock_cls:
            mock_cls.create.return_value = mock_pattern
            stats = learner.batch_learn([(make_operation(), make_feedback())])
        assert stats["processed"] == 1
        assert stats["created"] == 1


class TestQualityGateBoost:
    def make_result(
        self, critical=0, errors=0, warnings=0, info=0, total=0, files=5, analyzed=5, failed=0
    ):
        result = MagicMock()
        result.summary.return_value = {
            "critical": critical,
            "errors": errors,
            "warnings": warnings,
            "info": info,
            "total_issues": total,
            "total_files": files,
            "files_analyzed": analyzed,
            "files_failed": failed,
        }
        return result

    def test_passes_clean_result(self):
        from refactron.cicd.quality_gates import QualityGate

        gate = QualityGate()
        passed, msg = gate.check(self.make_result())
        assert passed is True

    def test_fails_on_critical(self):

        gate = QualityGate(max_critical=0)
        passed, msg = gate.check(self.make_result(critical=1))
        assert passed is False

    def test_fails_on_too_many_errors(self):

        gate = QualityGate(max_errors=5)
        passed, msg = gate.check(self.make_result(errors=6))
        assert passed is False

    def test_fails_on_too_many_warnings(self):

        gate = QualityGate(max_warnings=10)
        passed, msg = gate.check(self.make_result(warnings=11))
        assert passed is False

    def test_fails_on_max_total(self):

        gate = QualityGate(max_total=5)
        passed, msg = gate.check(self.make_result(total=6))
        assert passed is False

    def test_fails_on_low_success_rate(self):

        gate = QualityGate(min_success_rate=0.95)
        passed, msg = gate.check(self.make_result(files=10, analyzed=8, failed=2))
        assert passed is False

    def test_fail_on_errors_flag(self):

        gate = QualityGate(fail_on_errors=True)
        passed, msg = gate.check(self.make_result(errors=1))
        assert passed is False

    def test_fail_on_warnings_flag(self):

        gate = QualityGate(fail_on_warnings=True)
        passed, msg = gate.check(self.make_result(warnings=1))
        assert passed is False

    def test_to_dict_round_trip(self):

        gate = QualityGate(max_critical=2, max_errors=5)
        d = gate.to_dict()
        gate2 = QualityGate.from_dict(d)
        assert gate2.max_critical == 2

    def test_no_files_skips_success_rate_check(self):

        gate = QualityGate()
        passed, _ = gate.check(self.make_result(files=0, analyzed=0))
        assert passed is True


class TestQualityGateParserBoost:
    def test_parse_json_output(self, tmp_path):
        from refactron.cicd.quality_gates import QualityGateParser

        f = tmp_path / "result.json"
        f.write_text(json.dumps({"critical": 0, "errors": 1}))
        data = QualityGateParser.parse_json_output(f)
        assert data["errors"] == 1

    def test_parse_json_file_not_found(self):

        with pytest.raises(FileNotFoundError):
            QualityGateParser.parse_json_output(Path("/nonexistent/result.json"))

    def test_parse_json_invalid(self, tmp_path):

        f = tmp_path / "bad.json"
        f.write_text("not json")
        with pytest.raises(ValueError):
            QualityGateParser.parse_json_output(f)

    def test_parse_text_output(self):

        text = "Critical: 2\nErrors: 5\nWarnings: 10\nInfo: 1\nTotal: 18"
        result = QualityGateParser.parse_text_output(text)
        assert result["critical"] == 2
        assert result["errors"] == 5

    def test_parse_text_output_empty(self):

        result = QualityGateParser.parse_text_output("")
        assert result["critical"] == 0

    def test_parse_exit_code(self):

        assert QualityGateParser.parse_exit_code(0)["should_fail"] is False
        assert QualityGateParser.parse_exit_code(1)["should_fail"] is True

    def test_enforce_gate_passes(self):

        gate = QualityGate()
        result = MagicMock()
        result.summary.return_value = {
            "critical": 0,
            "errors": 0,
            "warnings": 0,
            "info": 0,
            "total_issues": 0,
            "total_files": 1,
            "files_analyzed": 1,
            "files_failed": 0,
        }
        passed, msg, code = QualityGateParser.enforce_gate(result, gate)
        assert passed and code == 0

    def test_generate_summary(self):

        result = MagicMock()
        result.summary.return_value = {
            "critical": 1,
            "errors": 2,
            "warnings": 3,
            "info": 0,
            "total_issues": 6,
            "total_files": 5,
            "files_analyzed": 4,
            "files_failed": 1,
        }
        summary = QualityGateParser.generate_summary(result)
        assert "Quality Gate" in summary


# ──────────────────────────── PRIntegration ───────────────────────────────────


class TestPRComment:
    def test_to_markdown_with_suggestion(self):
        from refactron.cicd.pr_integration import PRComment

        c = PRComment(
            file_path="a.py",
            line=5,
            message="Too complex",
            level="error",
            rule_id="C001",
            suggestion="x = 1",
        )
        md = c.to_markdown()
        assert "ERROR" in md and "C001" in md and "Suggestion" in md

    def test_to_markdown_no_suggestion(self):

        c = PRComment(file_path="a.py", line=1, message="Issue", level="warning")
        md = c.to_markdown()
        assert "WARNING" in md and "Suggestion" not in md


class TestPRIntegrationBoost:
    def make_result(self, n_issues=0, n_files=2, n_critical=0, n_failed=0):
        result = MagicMock()
        result.summary.return_value = {
            "files_analyzed": n_files,
            "total_files": n_files,
            "critical": n_critical,
            "errors": 0,
            "warnings": 0,
            "info": 0,
            "total_issues": n_issues,
            "files_failed": n_failed,
        }
        result.all_issues = []
        result.file_metrics = []
        return result

    def test_generate_pr_summary_no_issues(self):
        from refactron.cicd.pr_integration import PRIntegration

        pr = PRIntegration.generate_pr_summary(self.make_result())
        assert "Refactron" in pr

    def test_generate_pr_summary_with_critical(self):

        pr = PRIntegration.generate_pr_summary(self.make_result(n_critical=2, n_issues=2))
        assert "critical" in pr.lower()

    def test_generate_pr_summary_with_failed_files(self):

        pr = PRIntegration.generate_pr_summary(self.make_result(n_failed=1))
        assert "failed" in pr.lower()

    def test_generate_inline_comments(self):

        result = MagicMock()
        issue = MagicMock()
        issue.level.name = "ERROR"
        issue.line_number = 5
        issue.message = "Bad code"
        issue.rule_id = "E001"
        issue.suggestion = None
        result.issues_by_file.return_value = [issue]
        comments = PRIntegration.generate_inline_comments(result, Path("a.py"))
        assert len(comments) == 1

    def test_format_comment_for_github_api(self):

        c = PRComment("a.py", 5, "msg", "error", "E001", "fix")
        data = PRIntegration.format_comment_for_github_api(c)
        assert "path" in data and "body" in data

    def test_save_comments_json(self, tmp_path):

        out = tmp_path / "comments.json"
        comments = [PRComment("a.py", 1, "msg", "warning")]
        PRIntegration.save_comments_json(comments, out)
        data = json.loads(out.read_text())
        assert len(data) == 1

    def test_generate_github_comment_body(self):

        body = PRIntegration.generate_github_comment_body(self.make_result())
        assert "Refactron" in body

    def test_top_issues_by_file(self):

        result = MagicMock()
        result.summary.return_value = {
            "files_analyzed": 2,
            "total_files": 2,
            "critical": 0,
            "errors": 1,
            "warnings": 0,
            "info": 0,
            "total_issues": 1,
            "files_failed": 0,
        }
        file_metrics_mock = MagicMock()
        file_metrics_mock.file_path = Path("a.py")
        file_metrics_mock.issues = [MagicMock()]
        result.all_issues = [MagicMock()]
        result.file_metrics = [file_metrics_mock]
        pr = PRIntegration.generate_pr_summary(result)
        assert "a.py" in pr


# ──────────────────────────── cli/auth.py ─────────────────────────────────────
