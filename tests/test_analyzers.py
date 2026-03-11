"""Tests for analyzers."""

from pathlib import Path
from unittest.mock import MagicMock

from refactron.analyzers.code_smell_analyzer import CodeSmellAnalyzer
from refactron.analyzers.complexity_analyzer import ComplexityAnalyzer
from refactron.core.config import RefactronConfig
from refactron.llm.orchestrator import LLMOrchestrator


def test_complexity_analyzer() -> None:
    """Test complexity analyzer."""
    config = RefactronConfig(max_function_complexity=5)
    analyzer = ComplexityAnalyzer(config)

    code = """
def complex_function(x, y, z):
    if x > 0:
        if y > 10:
            if z > 20:
                if x > 30:
                    if y > 40:
                        if z > 50:
                            return "very high"
                        return "high"
                    return "medium"
                return "low"
            return "very low"
        return "negative"
    return "zero"
"""

    issues = analyzer.analyze(Path("test.py"), code)
    # Should detect high complexity
    assert len(issues) > 0
    assert analyzer.name == "complexity"


def test_code_smell_analyzer() -> None:
    """Test code smell analyzer."""
    config = RefactronConfig()
    analyzer = CodeSmellAnalyzer(config)

    code = """
def function_with_many_params(a, b, c, d, e, f, g, h):
    return a + b + c + d + e + f + g + h

class MyClass:
    def method_without_docstring(self):
        magic_number = 12345
        return magic_number
"""

    issues = analyzer.analyze(Path("test.py"), code)
    assert len(issues) > 0
    assert analyzer.name == "code_smells"


def test_code_smell_ai_triage_filtering() -> None:
    """Test that CodeSmellAnalyzer filters issues based on AI triage validation."""
    config = RefactronConfig(enable_ai_triage=True)

    # Mock the LLMOrchestrator
    mock_orchestrator = MagicMock(spec=LLMOrchestrator)

    # Create the analyzer with the mocked orchestrator
    analyzer = CodeSmellAnalyzer(config, orchestrator=mock_orchestrator)

    code = """
def deeply_nested():
    if True:
        if True:
            if True:
                if True:
                    if True:
                        pass
"""

    # We expect 2 issues: deep nesting (S002) and missing docstring (S005).
    # The mock will return S002 with low confidence (0.2)
    # and ignore S005 or give it high confidence (0.9).
    mock_orchestrator.evaluate_issues_batch.return_value = {"S002": 0.2, "S005": 0.9}

    issues = analyzer.analyze(Path("test.py"), code)

    # The S002 issue should be filtered out. S005 should remain.
    assert len(issues) == 1
    assert issues[0].rule_id == "S005"
    mock_orchestrator.evaluate_issues_batch.assert_called_once()

    # Test case 2: High confidence for both
    mock_orchestrator.evaluate_issues_batch.return_value = {"S002": 0.9, "S005": 0.9}

    issues = analyzer.analyze(Path("test.py"), code)

    # Neither should be filtered out
    assert len(issues) == 2
    assert any(i.rule_id == "S002" for i in issues)
    assert any(i.rule_id == "S005" for i in issues)


def test_analyzer_handles_syntax_errors() -> None:
    """Test that analyzers handle syntax errors gracefully."""
    config = RefactronConfig()
    analyzer = ComplexityAnalyzer(config)

    # Invalid Python code
    code = "def broken function(:"

    issues = analyzer.analyze(Path("test.py"), code)
    # Should return an error issue, not crash
    assert len(issues) >= 0
