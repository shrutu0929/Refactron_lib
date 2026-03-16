"""
Auto-fix engine for applying rule-based code transformations.

This engine uses AST analysis and pattern matching to apply safe
automatic fixes without requiring expensive AI APIs.
"""

import time
from typing import Callable, Dict, List, Optional

from refactron.autofix.models import (
    BatchFixReport,
    FixResult,
    FixRiskLevel,
)
from refactron.core.models import CodeIssue


class AutoFixEngine:
    """
    Engine for applying automatic fixes to code issues.

    All fixes use rule-based AST transformations for reliability
    and performance. No expensive AI APIs required!
    """

    def __init__(self, safety_level: FixRiskLevel = FixRiskLevel.SAFE):
        """
        Initialize the auto-fix engine.

        Args:
            safety_level: Maximum risk level to apply automatically
        """
        self.safety_level = safety_level
        self.fixers = self._register_fixers()

    def _register_fixers(self) -> Dict[str, "BaseFixer"]:
        """Register all available fixers."""
        from refactron.autofix.fixers import (
            AddDocstringsFixer,
            AddMissingCommasFixer,
            ConvertToFStringFixer,
            ExtractMagicNumbersFixer,
            FixIndentationFixer,
            FixTypeHintsFixer,
            NormalizeQuotesFixer,
            RemoveDeadCodeFixer,
            RemovePrintStatementsFixer,
            RemoveTrailingWhitespaceFixer,
            RemoveUnusedImportsFixer,
            RemoveUnusedVariablesFixer,
            SimplifyBooleanFixer,
            SortImportsFixer,
        )

        fixers = {}
        for fixer_class in [
            RemoveUnusedImportsFixer,
            ExtractMagicNumbersFixer,
            AddDocstringsFixer,
            RemoveDeadCodeFixer,
            FixTypeHintsFixer,
            SortImportsFixer,
            RemoveTrailingWhitespaceFixer,
            NormalizeQuotesFixer,
            SimplifyBooleanFixer,
            ConvertToFStringFixer,
            RemoveUnusedVariablesFixer,
            FixIndentationFixer,
            AddMissingCommasFixer,
            RemovePrintStatementsFixer,
        ]:
            fixer = fixer_class()
            fixers[fixer.name] = fixer

        return fixers

    def can_fix(self, issue: CodeIssue) -> bool:
        """
        Check if an issue can be auto-fixed.

        Args:
            issue: The issue to check

        Returns:
            True if a fixer is available, False otherwise
        """
        return issue.rule_id in self.fixers if issue.rule_id else False

    def fix(self, issue: CodeIssue, code: str, preview: bool = True) -> FixResult:
        """
        Apply automatic fix to an issue.

        Args:
            issue: The issue to fix
            code: The original code
            preview: If True, only preview changes (don't apply)

        Returns:
            FixResult with success status and details
        """
        if not self.can_fix(issue):
            return FixResult(
                success=False, reason=f"No fixer available for issue: {issue.rule_id or 'unknown'}"
            )
        assert issue.rule_id is not None
        fixer = self.fixers[issue.rule_id]

        # Check risk level
        if fixer.risk_score > self.safety_level.value:
            return FixResult(
                success=False,
                reason=(
                    f"Fix risk level ({fixer.risk_score}) exceeds safety level "
                    f"({self.safety_level.value})"
                ),
            )

        # Apply fix
        if preview:
            return fixer.preview(issue, code)
        return fixer.apply(issue, code)

    def fix_all(self, issues: list, code: str, preview: bool = True) -> Dict[int, FixResult]:
        """
        Apply fixes to multiple issues.

        Args:
            issues: List of issues to fix
            code: The original code
            preview: If True, only preview changes

        Returns:
            Dictionary mapping issue index to fix result
        """
        results = {}

        for idx, issue in enumerate(issues):
            if self.can_fix(issue):
                results[idx] = self.fix(issue, code, preview)
            else:
                results[idx] = FixResult(success=False, reason="No fixer available")

        return results

    def fix_batch_with_report(
        self,
        issues: List[CodeIssue],
        code: str,
        file_path: Optional[str] = None,
    ) -> BatchFixReport:
        """Apply fixes to all fixable issues and return a detailed summary report.

        Args:
            issues: List of CodeIssue objects to attempt to fix
            code: The original source code string
            file_path: Optional file path for context (used in stats)

        Returns:
            BatchFixReport with per-issue results and aggregate stats
        """
        report = BatchFixReport()
        start_time = time.time()
        current_code = code
        files_touched = set()

        for idx, issue in enumerate(issues):
            if not self.can_fix(issue):
                result = FixResult(success=False, reason="No fixer available")
                report.stats.skipped += 1
            else:
                result = self.fix(issue, current_code, preview=False)
                if result.success:
                    report.stats.successful += 1
                    if result.fixed:
                        current_code = result.fixed
                    if file_path:
                        files_touched.add(file_path)
                else:
                    report.stats.failed += 1

            report.stats.total += 1
            report.results[idx] = result

        report.stats.files_affected = len(files_touched)
        report.stats.duration_seconds = time.time() - start_time
        return report

    def fix_interactive(
        self,
        issues: List[CodeIssue],
        code: str,
        confirm_callback: Optional[Callable[[int, str, str], bool]] = None,
    ) -> BatchFixReport:
        """Preview each fix as a diff and optionally apply based on user confirmation.

        Args:
            issues: List of CodeIssue objects to attempt to fix
            code: The original source code string
            confirm_callback: Optional callable(issue_idx, diff, reason) -> bool.
                If None, all previews are collected but NOT applied (dry-run mode).

        Returns:
            BatchFixReport with pending_diffs list for user review and any applied results
        """
        report = BatchFixReport()
        start_time = time.time()
        current_code = code

        for idx, issue in enumerate(issues):
            if not self.can_fix(issue):
                result = FixResult(success=False, reason="No fixer available")
                report.stats.skipped += 1
                report.results[idx] = result
                report.stats.total += 1
                continue

            # Always preview first to generate the diff
            preview_result = self.fix(issue, current_code, preview=True)

            if not preview_result.success or not preview_result.diff:
                report.stats.failed += 1
                report.results[idx] = preview_result
                report.stats.total += 1
                continue

            # Store diff for user review regardless of confirmation
            diff_entry = {
                "index": idx,
                "issue": issue.message,
                "rule_id": issue.rule_id,
                "line": issue.line_number,
                "reason": preview_result.reason,
                "diff": preview_result.diff,
                "risk_score": preview_result.risk_score,
            }
            report.pending_diffs.append(diff_entry)

            # Apply if confirmed
            approved = (
                confirm_callback(idx, preview_result.diff, preview_result.reason)
                if confirm_callback
                else False
            )

            if approved:
                apply_result = self.fix(issue, current_code, preview=False)
                if apply_result.success and apply_result.fixed:
                    current_code = apply_result.fixed
                    report.stats.successful += 1
                    report.results[idx] = apply_result
                else:
                    report.stats.failed += 1
                    report.results[idx] = apply_result
            else:
                # Not applied — treat as skipped for stats
                report.stats.skipped += 1
                report.results[idx] = FixResult(
                    success=False,
                    reason="Pending user confirmation",
                    diff=preview_result.diff,
                    original=preview_result.original,
                )

            report.stats.total += 1

        report.stats.duration_seconds = time.time() - start_time
        return report


class BaseFixer:
    """Base class for all automatic fixers."""

    def __init__(self, name: str, risk_score: float = 0.0):
        """
        Initialize a fixer.

        Args:
            name: Name of the fixer
            risk_score: Risk level (0.0 = safe, 1.0 = dangerous)
        """
        self.name = name
        self.risk_score = risk_score

    def preview(self, issue: CodeIssue, code: str) -> FixResult:
        """
        Preview the fix without applying it.

        Args:
            issue: The issue to fix
            code: The original code

        Returns:
            FixResult with diff showing proposed changes
        """
        raise NotImplementedError

    def apply(self, issue: CodeIssue, code: str) -> FixResult:
        """
        Apply the fix.

        Args:
            issue: The issue to fix
            code: The original code

        Returns:
            FixResult with fixed code
        """
        raise NotImplementedError
