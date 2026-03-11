import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from refactron.analyzers.code_smell_analyzer import CodeSmellAnalyzer
from refactron.autofix.engine import AutoFixEngine
from refactron.core.config import RefactronConfig
from refactron.core.models import CodeIssue, IssueCategory, IssueLevel
from refactron.llm.models import RefactoringSuggestion, SuggestionStatus


class TestAIAutoFixIntegration(unittest.TestCase):
    """Integration tests for AI-triggered auto-fixes."""

    def setUp(self):
        self.config = RefactronConfig()  # Fresh config
        self.config.enable_ai_triage = True
        self.orchestrator = MagicMock()
        self.analyzer = CodeSmellAnalyzer(self.config, self.orchestrator)
        # Use a higher safety level to allow AI suggestions (0.5)
        from refactron.autofix.models import FixRiskLevel
        self.engine = AutoFixEngine(safety_level=FixRiskLevel.HIGH)

    def test_high_confidence_magic_number_triggers_suggestion(self):
        """Test that a high-confidence magic number triggers an AI suggestion."""
        source_code = "def area(radius):\n    return 3.14159 * radius * radius"
        file_path = Path("test_file.py")

        # Mock AI triage to return high confidence (0.9) for the magic number (rule S004)
        # and low confidence for other issues (like missing docstring S005)
        self.orchestrator.evaluate_issues_batch.return_value = {"S004": 0.9, "S005": 0.5}

        # Mock AI suggestion generation
        proposed_code = "PI = 3.14159\n\ndef area(radius):\n    return PI * radius * radius"
        suggestion = RefactoringSuggestion(
            issue=MagicMock(spec=CodeIssue),
            original_code=source_code,
            context_files=[],
            proposed_code=proposed_code,
            explanation="Extracted magic number 3.14159 to constant PI",
            reasoning="Magic numbers reduce maintainability. Using a named constant is better.",
            model_name="mock-model",
            confidence_score=0.9,
            status=SuggestionStatus.PENDING
        )
        self.orchestrator.generate_suggestion.return_value = suggestion

        # Run analysis
        issues = self.analyzer.analyze(file_path, source_code)

        # Verify magic number issue was detected and has a suggestion
        magic_number_issue = next((i for i in issues if i.rule_id == "S004"), None)
        self.assertIsNotNone(magic_number_issue)
        self.assertEqual(magic_number_issue.suggestion, proposed_code)
        self.assertTrue(magic_number_issue.metadata.get("ai_fix_available"))

        # Verify engine can fix it using the AI suggestion
        self.assertTrue(self.engine.can_fix(magic_number_issue))
        
        # Apply the fix
        result = self.engine.fix(magic_number_issue, source_code, preview=False)
        
        self.assertTrue(result.success, f"Fix failed: {result.reason}")
        self.assertEqual(result.fixed, proposed_code)
        self.assertIn("PI = 3.14159", result.fixed)
        self.assertIn("PI * radius * radius", result.fixed)

    def test_low_confidence_does_not_trigger_suggestion(self):
        """Test that a low-confidence issue does not trigger an AI suggestion."""
        source_code = "def area(radius):\n    return 3.14159 * radius * radius"
        file_path = Path("test_file.py")

        # Confidence (0.5) is above filtered threshold (0.3) but below auto-fix threshold (0.8)
        # Also mock S005 to be low confidence
        self.orchestrator.evaluate_issues_batch.return_value = {"S004": 0.5, "S005": 0.1}

        # Run analysis
        issues = self.analyzer.analyze(file_path, source_code)

        # Verify magic number issue exists but NO suggestion was generated (stays default)
        magic_number_issue = next((i for i in issues if i.rule_id == "S004"), None)
        self.assertIsNotNone(magic_number_issue)
        self.assertEqual(magic_number_issue.suggestion, "Consider extracting this number into a named constant.")
        self.orchestrator.generate_suggestion.assert_not_called()


if __name__ == "__main__":
    unittest.main()
