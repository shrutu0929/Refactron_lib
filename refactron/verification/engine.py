import ast
from dataclasses import dataclass
from typing import List, Optional

@dataclass(frozen=True)
class VerificationContext:
    original_code: str
    transformed_code: str
    original_ast: Optional[ast.AST]
    transformed_ast: Optional[ast.AST]

class BaseCheck:
    def verify(self, original: str, transformed: str, context: Optional[VerificationContext] = None) -> bool:
        """
        Verify the transformation. 
        Backward compatible Signature allows checks to drop the context argument if unsupported by custom checks.
        """
        raise NotImplementedError

class VerificationEngine:
    def __init__(self, checks: List[BaseCheck]):
        self.checks = checks
        
    def verify(self, original: str, transformed: str) -> bool:
        """
        Run all verification checks on the original and transformed code,
        parsing the AST only once to improve performance.
        """
        try:
            orig_ast = ast.parse(original)
        except Exception:
            orig_ast = None
            
        try:
            trans_ast = ast.parse(transformed)
        except Exception:
            trans_ast = None
            
        context = VerificationContext(
            original_code=original,
            transformed_code=transformed,
            original_ast=orig_ast,
            transformed_ast=trans_ast
        )
        
        all_passed = True
        for check in self.checks:
            try:
                # Attempt to pass context for optimized routines
                passed = check.verify(original, transformed, context=context)
            except TypeError:
                # Fallback for older checks that don't accept context
                passed = check.verify(original, transformed)
                
            if not passed:
                all_passed = False
                
        return all_passed
"""VerificationEngine — pipeline orchestrator for verification checks."""

import math
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

from refactron.verification.result import CheckResult, VerificationResult


class BaseCheck(ABC):
    """Abstract base class for all verification checks."""

    name: str

    @abstractmethod
    def verify(self, original: str, transformed: str, file_path: Path) -> CheckResult:
        """Run this check and return a CheckResult."""
        ...


class VerificationEngine:
    """Orchestrates verification checks in a short-circuit pipeline."""

    def __init__(
        self,
        project_root: Optional[Path] = None,
        checks: Optional[List[BaseCheck]] = None,
    ):
        self.project_root = project_root
        self.checks: List[BaseCheck]
        if checks is not None:
            self.checks = checks
        else:
            from refactron.verification.checks.imports import ImportIntegrityVerifier
            from refactron.verification.checks.syntax import SyntaxVerifier
            from refactron.verification.checks.test_gate import TestSuiteGate

            self.checks = [
                SyntaxVerifier(),
                ImportIntegrityVerifier(),
                TestSuiteGate(project_root=project_root),
            ]

    def verify(self, original: str, transformed: str, file_path: Path) -> VerificationResult:
        """Run all checks in order, short-circuiting on first failure."""
        start = time.monotonic()
        check_results: List[CheckResult] = []
        checks_run: List[str] = []
        checks_passed: List[str] = []
        checks_failed: List[str] = []
        skipped_checks: List[tuple] = []
        blocking_reason: Optional[str] = None
        passed = True

        for i, check in enumerate(self.checks):
            try:
                cr = check.verify(original, transformed, file_path)
            except Exception as exc:
                cr = CheckResult(
                    check_name=check.name,
                    passed=False,
                    blocking_reason=f"Check raised exception: {exc}",
                    confidence=0.0,
                    duration_ms=0,
                    details={"exception": str(exc)},
                )
                passed = False

            check_results.append(cr)
            checks_run.append(check.name)

            if cr.passed:
                checks_passed.append(check.name)
            else:
                checks_failed.append(check.name)
                if blocking_reason is None:
                    blocking_reason = cr.blocking_reason
                # Short-circuit: skip remaining checks
                for remaining in self.checks[i + 1 :]:
                    skipped_checks.append(
                        (remaining.name, f"Short-circuited after {check.name} failed")
                    )
                break

        elapsed_ms = int((time.monotonic() - start) * 1000)
        confidence = self._compute_confidence(check_results)
        safe = passed and len(checks_failed) == 0

        return VerificationResult(
            safe_to_apply=safe,
            passed=passed,
            checks_run=checks_run,
            checks_passed=checks_passed,
            checks_failed=checks_failed,
            skipped_checks=skipped_checks,
            blocking_reason=blocking_reason,
            confidence_score=confidence,
            verification_ms=elapsed_ms,
            check_results=check_results,
        )

    @staticmethod
    def _compute_confidence(results: List[CheckResult]) -> float:
        """Geometric mean of passed checks' confidence. 0.0 if none passed."""
        passed = [r.confidence for r in results if r.passed]
        if not passed:
            return 0.0
        return float(math.prod(passed) ** (1.0 / len(passed)))
