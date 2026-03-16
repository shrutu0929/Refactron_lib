"""
Auto-fix module for automatically fixing code issues.

This module provides rule-based code fixes without requiring expensive AI APIs.
All fixers use AST analysis and pattern matching for fast, reliable
transformations.
"""

from refactron.autofix.engine import AutoFixEngine, FixResult
from refactron.autofix.fixers import (
    AddDocstringsFixer,
    ExtractMagicNumbersFixer,
    FixTypeHintsFixer,
    RemoveDeadCodeFixer,
    RemoveUnusedImportsFixer,
)
from refactron.autofix.models import BatchFixReport, FixStats

__all__ = [
    "AutoFixEngine",
    "FixResult",
    "FixStats",
    "BatchFixReport",
    "RemoveUnusedImportsFixer",
    "ExtractMagicNumbersFixer",
    "AddDocstringsFixer",
    "RemoveDeadCodeFixer",
    "FixTypeHintsFixer",
]
