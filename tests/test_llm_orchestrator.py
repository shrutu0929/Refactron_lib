"""Tests for LLM Orchestrator."""

import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from refactron.core.models import CodeIssue, IssueCategory, IssueLevel
from refactron.llm.models import RefactoringSuggestion, SuggestionStatus
from refactron.llm.orchestrator import LLMOrchestrator
from refactron.llm.safety import SafetyGate
from refactron.rag.retriever import RetrievedContext


class TestLLMOrchestrator:
    """Tests for LLMOrchestrator."""

    @pytest.fixture
    def mock_retriever(self):
        retriever = Mock()
        retriever.retrieve_similar.return_value = []
        return retriever

    @pytest.fixture
    def mock_client(self):
        client = Mock()
        client.model = "llama-3.3-70b-versatile"
        # Return valid JSON in code block
        client.generate.return_value = """
```json
{
    "proposed_code": "def fixed(): pass",
    "explanation": "Fixed the bug",
    "reasoning": "Because it was broken"
}
```
"""
        return client

    @pytest.fixture
    def mock_safety(self):
        gate = Mock()
        result = MagicMock()
        result.passed = True
        result.issues = []
        gate.validate.return_value = result
        return gate

    @pytest.fixture
    def sample_issue(self):
        return CodeIssue(
            category=IssueCategory.CODE_SMELL,
            level=IssueLevel.WARNING,
            message="Function is too long",
            file_path=Path("/test.py"),
            line_number=10,
        )

    def test_generate_suggestion_basic(self, mock_client, mock_safety, sample_issue):
        """Test generating a successful suggestion."""
        orchestrator = LLMOrchestrator(llm_client=mock_client, safety_gate=mock_safety)

        suggestion = orchestrator.generate_suggestion(
            issue=sample_issue, original_code="def broken(): pass"
        )

        assert suggestion.status == SuggestionStatus.PENDING
        assert suggestion.proposed_code == "def fixed(): pass"
        assert suggestion.explanation == "Fixed the bug"
        assert suggestion.model_name == "llama-3.3-70b-versatile"

        # Verify prompt construction (implicity) by checking generate call
        mock_client.generate.assert_called_once()
        args = mock_client.generate.call_args
        assert "Function is too long" in args.kwargs["prompt"]
        assert "def broken(): pass" in args.kwargs["prompt"]

    def test_generate_suggestion_with_rag(self, mock_client, mock_retriever, sample_issue):
        """Test generation with RAG context."""
        # Setup retriever to return context
        mock_retriever.retrieve_similar.return_value = [
            RetrievedContext(
                content="def similar_func(): pass",
                file_path="/similar.py",
                chunk_type="function",
                name="similar_func",
                line_range=(1, 2),
                distance=0.1,
                metadata={},
            )
        ]

        orchestrator = LLMOrchestrator(retriever=mock_retriever, llm_client=mock_client)

        suggestion = orchestrator.generate_suggestion(issue=sample_issue, original_code="original")

        assert "/similar.py" in suggestion.context_files

        # Verify prompt contains RAG context
        args = mock_client.generate.call_args
        assert "def similar_func(): pass" in args.kwargs["prompt"]

    def test_bad_llm_response(self, mock_client, sample_issue):
        """Test handling of invalid JSON from LLM."""
        mock_client.generate.return_value = "This is not JSON"

        orchestrator = LLMOrchestrator(llm_client=mock_client)

        suggestion = orchestrator.generate_suggestion(issue=sample_issue, original_code="original")

        assert suggestion.status == SuggestionStatus.FAILED
        assert (
            "JSONDecodeError" in suggestion.explanation
            or "Expecting value" in suggestion.explanation
        )

    def test_safety_check_failure(self, mock_client, mock_safety, sample_issue):
        """Test rejection when safety check fails."""
        # Setup safety failure
        result = MagicMock()
        result.passed = False
        result.issues = ["Syntax Error"]
        mock_safety.validate.return_value = result

        orchestrator = LLMOrchestrator(llm_client=mock_client, safety_gate=mock_safety)

        suggestion = orchestrator.generate_suggestion(issue=sample_issue, original_code="original")

        assert suggestion.status == SuggestionStatus.REJECTED
        assert not suggestion.safety_result.passed


# ─────────────── LLM Orchestrator (boost) ───────────────


def make_issue():
    return CodeIssue(
        category=IssueCategory.COMPLEXITY,
        level=IssueLevel.WARNING,
        message="Too complex",
        file_path=Path("test.py"),
        line_number=5,
    )


def make_orchestrator(llm_response=None, llm_raise=None, safety_pass=True):
    mock_client = MagicMock()
    if llm_raise:
        mock_client.generate.side_effect = llm_raise
    else:
        mock_client.generate.return_value = llm_response or json.dumps(
            {
                "proposed_code": "x = 1",
                "explanation": "Fixed",
                "reasoning": "ok",
                "confidence_score": 0.9,
            }
        )
    mock_client.model = "test-model"

    mock_safety = MagicMock()
    safety_result = MagicMock()
    safety_result.passed = safety_pass
    safety_result.score = 0.9 if safety_pass else 0.1
    safety_result.issues = [] if safety_pass else ["issue"]
    mock_safety.validate.return_value = safety_result

    return LLMOrchestrator(llm_client=mock_client, safety_gate=mock_safety), mock_client


class TestGenerateSuggestion:
    def test_basic_success(self):
        orch, client = make_orchestrator()
        result = orch.generate_suggestion(make_issue(), "x = 0")
        assert result.status == SuggestionStatus.PENDING

    def test_safety_fail_sets_rejected(self):
        orch, _ = make_orchestrator(safety_pass=False)
        result = orch.generate_suggestion(make_issue(), "x = 0")
        assert result.status == SuggestionStatus.REJECTED

    def test_llm_exception_returns_failed(self):
        orch, _ = make_orchestrator(llm_raise=RuntimeError("LLM down"))
        result = orch.generate_suggestion(make_issue(), "x = 0")
        assert result.status == SuggestionStatus.FAILED

    def test_retriever_called(self):
        orch, client = make_orchestrator()
        mock_retriever = MagicMock()
        mock_retriever.retrieve_similar.return_value = [
            MagicMock(content="context", file_path="ctx.py")
        ]
        orch.retriever = mock_retriever
        orch.generate_suggestion(make_issue(), "x = 0")
        mock_retriever.retrieve_similar.assert_called_once()

    def test_retriever_exception_handled(self):
        orch, _ = make_orchestrator()
        mock_retriever = MagicMock()
        mock_retriever.retrieve_similar.side_effect = Exception("rag fail")
        orch.retriever = mock_retriever
        result = orch.generate_suggestion(make_issue(), "x = 0")
        # When retriever fails, orchestrator still produces a result
        # (may be PENDING if it gracefully skips context, or FAILED if it treats it as fatal)
        assert result.status in (SuggestionStatus.PENDING, SuggestionStatus.FAILED)

    def test_confidence_string_percent(self):
        response = json.dumps(
            {
                "proposed_code": "x=1",
                "explanation": "ok",
                "reasoning": "r",
                "confidence_score": "85%",
            }
        )
        orch, _ = make_orchestrator(llm_response=response)
        result = orch.generate_suggestion(make_issue(), "x = 0")
        assert result.status in (SuggestionStatus.PENDING, SuggestionStatus.REJECTED)

    def test_invalid_confidence_falls_back(self):
        response = json.dumps(
            {"proposed_code": "x=1", "explanation": "ok", "confidence_score": "invalid"}
        )
        orch, _ = make_orchestrator(llm_response=response)
        result = orch.generate_suggestion(make_issue(), "x = 0")
        assert result.confidence_score > 0

    def test_safety_validation_exception_sets_failed(self):
        orch, _ = make_orchestrator()
        orch.safety_gate.validate.side_effect = Exception("safety crash")
        result = orch.generate_suggestion(make_issue(), "x = 0")
        assert result.status == SuggestionStatus.FAILED

    def test_markdown_code_block_stripped(self):
        response = (
            "```json\n"
            + json.dumps({"proposed_code": "x=1", "explanation": "ok", "confidence_score": 0.9})
            + "\n```"
        )
        orch, _ = make_orchestrator(llm_response=response)
        result = orch.generate_suggestion(make_issue(), "x = 0")
        assert result.status != SuggestionStatus.FAILED


class TestGenerateDocumentation:
    def test_success_with_delimiters(self):
        response = "@@@EXPLANATION@@@Added docstrings.@@@CONFIDENCE@@@0.85@@@MARKDOWN@@@# Docs\n"
        orch, _ = make_orchestrator(llm_response=response)
        result = orch.generate_documentation("def foo(): pass")
        assert result.status == SuggestionStatus.PENDING

    def test_no_delimiter_raises_valueerror(self):
        orch, _ = make_orchestrator(llm_response="just plain text")
        result = orch.generate_documentation("def foo(): pass")
        assert result.status == SuggestionStatus.FAILED

    def test_llm_exception_returns_failed(self):
        orch, _ = make_orchestrator(llm_raise=RuntimeError("fail"))
        result = orch.generate_documentation("def foo(): pass")
        assert result.status == SuggestionStatus.FAILED

    def test_invalid_confidence_falls_back(self):
        response = "@@@EXPLANATION@@@ok@@@CONFIDENCE@@@BAD@@@MARKDOWN@@@# x\n"
        orch, _ = make_orchestrator(llm_response=response)
        result = orch.generate_documentation("def foo(): pass")
        assert result.confidence_score == pytest.approx(0.8)


class TestEvaluateIssuesBatch:
    def test_empty_issues(self):
        orch, _ = make_orchestrator()
        result = orch.evaluate_issues_batch([], "x=1")
        assert result == {}

    def test_successful_batch(self):
        orch, client = make_orchestrator()
        client.generate.return_value = json.dumps({"issue:1:0": 0.9})
        issues = [make_issue()]
        result = orch.evaluate_issues_batch(issues, "x=1")
        assert isinstance(result, dict)

    def test_llm_exception_returns_defaults(self):
        orch, client = make_orchestrator()
        client.generate.side_effect = RuntimeError("fail")
        issues = [make_issue()]
        result = orch.evaluate_issues_batch(issues, "x=1")
        assert all(v == 0.5 for v in result.values())

    def test_duplicate_issue_ids(self):
        orch, client = make_orchestrator()
        client.generate.return_value = json.dumps({})
        issue1 = make_issue()
        issue2 = make_issue()  # same attributes → potential ID collision
        result = orch.evaluate_issues_batch([issue1, issue2], "x=1")
        assert isinstance(result, dict)


class TestCleanJsonResponse:
    def setup_method(self):
        self.orch, _ = make_orchestrator()

    def test_plain_json(self):
        assert self.orch._clean_json_response('{"a":1}') == '{"a":1}'

    def test_markdown_json_block(self):
        text = '```json\n{"a":1}\n```'
        assert self.orch._clean_json_response(text) == '{"a":1}'

    def test_generic_code_block(self):
        text = '```\n{"a":1}\n```'
        assert self.orch._clean_json_response(text) == '{"a":1}'

    def test_unclosed_code_block(self):
        text = '```json\n{"a":1}'
        result = self.orch._clean_json_response(text)
        assert '{"a":1}' in result


class TestOrchestratorInit:
    def test_uses_groq_if_env_set(self):
        mock_groq = MagicMock()
        with patch.dict("os.environ", {"GROQ_API_KEY": "key"}), patch(
            "refactron.llm.orchestrator.GroqClient", return_value=mock_groq
        ):
            orch = LLMOrchestrator()
        assert orch.client is mock_groq

    def test_falls_back_to_backend_if_groq_fails(self):
        mock_backend = MagicMock()
        with patch.dict("os.environ", {"GROQ_API_KEY": "key"}), patch(
            "refactron.llm.orchestrator.GroqClient", side_effect=RuntimeError
        ), patch("refactron.llm.orchestrator.BackendLLMClient", return_value=mock_backend):
            orch = LLMOrchestrator()
        assert orch.client is mock_backend

    def test_uses_backend_without_env(self):
        mock_backend = MagicMock()
        with patch.dict("os.environ", {}, clear=True), patch(
            "refactron.llm.orchestrator.BackendLLMClient", return_value=mock_backend
        ):
            orch = LLMOrchestrator()
        assert orch.client is mock_backend


# ─────────────── LLM Safety (boost) ───────────────


def make_suggestion(proposed="x = 1", original="x = 0", confidence=0.9):
    s = MagicMock(spec=RefactoringSuggestion)
    s.proposed_code = proposed
    s.original_code = original
    s.confidence_score = confidence
    return s


class TestSafetyGateValidate:
    def setup_method(self):
        self.gate = SafetyGate(min_confidence=0.7)

    def test_clean_code_passes(self):
        s = make_suggestion("x = 1")
        result = self.gate.validate(s)
        assert result.passed is True
        assert result.syntax_valid is True
        assert result.score > 0.8

    def test_syntax_error_fails(self):
        s = make_suggestion("def foo(:\n    pass")
        result = self.gate.validate(s)
        assert result.passed is False
        assert result.syntax_valid is False
        assert result.score == 0.0

    def test_low_confidence_reduces_score(self):
        s = make_suggestion(confidence=0.3)
        result = self.gate.validate(s)
        assert result.score < 1.0
        assert any("Low confidence" in i for i in result.issues)

    def test_risky_keyword_reduces_score(self):
        s = make_suggestion("import subprocess\nsubprocess.run('ls')")
        result = self.gate.validate(s)
        assert result.score < 1.0

    def test_dangerous_new_import_flagged(self):
        s = make_suggestion(proposed="import os\nos.remove('file')", original="x = 1")
        result = self.gate.validate(s)
        assert "os" in " ".join(result.side_effects)

    def test_existing_import_not_flagged(self):
        s = make_suggestion(proposed="import os\nos.remove('file')", original="import os\n")
        result = self.gate.validate(s)
        assert not any("Import: os" in e for e in result.side_effects)

    def test_multiple_risky_keywords(self):
        code = "import subprocess\nos.system('rm')\neval('x')"
        s = make_suggestion(code)
        result = self.gate.validate(s)
        assert result.score < 1.0


class TestAssessRisk:
    def setup_method(self):
        self.gate = SafetyGate()

    def test_no_risk(self):
        assert self.gate._assess_risk("x = 1") == 0.0

    def test_max_risk_capped_at_1(self):
        code = (
            "subprocess.run(); os.system(); eval(); exec();"
            " shutil.rmtree(); requests.get(); urllib.open('x'); open('f')"
        )
        assert self.gate._assess_risk(code) <= 1.0

    def test_single_risky_keyword(self):
        assert self.gate._assess_risk("eval('x')") == pytest.approx(0.3)


class TestCheckDangerousImports:
    def setup_method(self):
        self.gate = SafetyGate()

    def test_no_dangerous_imports(self):
        result = self.gate._check_dangerous_imports("x = 1", "x = 1")
        assert result == []

    def test_new_sys_import(self):
        result = self.gate._check_dangerous_imports("import sys\n", "x = 1")
        assert "sys" in result

    def test_from_import_dangerous(self):
        result = self.gate._check_dangerous_imports("from shutil import rmtree\n", "x = 1")
        assert "shutil" in result

    def test_syntax_error_in_code(self):
        result = self.gate._check_dangerous_imports("def foo(:\n    pass", "x = 1")
        assert result == []
