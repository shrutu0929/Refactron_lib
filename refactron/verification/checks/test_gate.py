import ast
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional

_TEST_DISCOVERY_CACHE: Dict[str, Dict[str, List[Path]]] = {}

class TestSuiteGate:
    def __init__(self, search_root: Path, project_root: Optional[Path] = None, pytest_args: Optional[List[str]] = None):
        self.search_root = search_root
        self.project_root = project_root
        self.pytest_args = pytest_args or []

    def _imports_module(self, test_file: Path, target_module: str) -> bool:
        try:
            source_code = test_file.read_text(encoding="utf-8")
            tree = ast.parse(source_code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if target_module in alias.name:
                            return True
                elif isinstance(node, ast.ImportFrom):
                    if node.module and target_module in node.module:
                        return True
        except Exception:
            pass
        return False

    def _find_relevant_tests(self, target_module: str) -> List[Path]:
        cache_key = str(self.project_root.resolve()) if self.project_root else str(self.search_root.resolve())
        
        if cache_key in _TEST_DISCOVERY_CACHE and target_module in _TEST_DISCOVERY_CACHE[cache_key]:
            return _TEST_DISCOVERY_CACHE[cache_key][target_module]
            
        relevant_tests = []
        ignore_patterns = {"venv", ".venv", "site-packages", "node_modules", ".git", ".pytest_cache", "__pycache__"}
        
        for p in self.search_root.rglob("*.py"):
            if self.project_root and any(part in ignore_patterns for part in p.parts):
                continue
                    
            if p.is_file() and p.name.startswith("test_"):
                if self._imports_module(p, target_module):
                    relevant_tests.append(p)
                    
        if cache_key not in _TEST_DISCOVERY_CACHE:
            _TEST_DISCOVERY_CACHE[cache_key] = {}
            
        _TEST_DISCOVERY_CACHE[cache_key][target_module] = relevant_tests
        return relevant_tests

    def verify(self, module_name: str, file_path: Path) -> bool:
        tests = self._find_relevant_tests(module_name)
        if not tests:
            return True
        result = self._run_pytest(tests, file_path)
        return result.returncode == 0

    def _run_pytest(self, test_files: List[Path], context_file: Path) -> subprocess.CompletedProcess:
        """
        Run pytest on the discovered test files using the correct interpreter and working directory.
        """
        # Optimized: Use the current running host Python executable directly
        cmd = [sys.executable, "-m", "pytest"]
        
        # Optional: Append externally configured arguments
        if self.pytest_args:
            cmd.extend(self.pytest_args)
            
        # Add the targets
        cmd.extend([str(f.resolve()) for f in test_files])
        
        # Optimized: Dynamically scope cwd bounding
        if self.project_root and self.project_root.exists():
            cwd = str(self.project_root.resolve())
        elif self.search_root and self.search_root.exists():
            cwd = str(self.search_root.resolve())
        else:
            # Safe Fallback to current file parent
            cwd = str(context_file.parent.resolve())
            
        # Execute tests via subprocess and correctly map cwd
        return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
"""TestSuiteGate — Check 3: run relevant tests against transformed code."""

import ast
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from refactron.verification.engine import BaseCheck
from refactron.verification.result import CheckResult


class TestSuiteGate(BaseCheck):
    """Runs pytest on test files that import the changed module."""

    __test__ = False  # Prevent pytest from collecting this as a test class
    name = "test_gate"

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = project_root

    def verify(self, original: str, transformed: str, file_path: Path) -> CheckResult:
        start = time.monotonic()
        details: Dict[str, Any] = {}

        # Step 1-2: find test files that import this module
        test_files = self._find_relevant_tests(file_path)
        if not test_files:
            elapsed = int((time.monotonic() - start) * 1000)
            details["note"] = "No tests cover this module"
            return CheckResult(
                check_name=self.name,
                passed=True,
                blocking_reason="",
                confidence=0.9,
                duration_ms=elapsed,
                details=details,
            )

        details["test_files"] = [str(f) for f in test_files]

        # Step 4-10: swap-and-restore
        backup_path = file_path.with_suffix(".py.refactron_backup")

        try:
            # Backup original
            shutil.copy2(file_path, backup_path)

            # Swap in transformed code
            file_path.write_text(transformed, encoding="utf-8")

            # Delete .pyc cache
            self._clear_pycache(file_path)

            # Run pytest
            cmd = ["python3", "-m", "pytest", "-x", "-q"]
            cmd += [str(f) for f in test_files]
            result = subprocess.run(
                cmd,
                timeout=45,
                capture_output=True,
                text=True,
                env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                cwd=str(file_path.parent),
            )

            elapsed = int((time.monotonic() - start) * 1000)

            if result.returncode == 0:
                details["tests_passed"] = True
                return CheckResult(
                    check_name=self.name,
                    passed=True,
                    blocking_reason="",
                    confidence=0.9,
                    duration_ms=elapsed,
                    details=details,
                )
            else:
                output = (result.stdout + result.stderr)[:500]
                details["test_output"] = output
                return CheckResult(
                    check_name=self.name,
                    passed=False,
                    blocking_reason=f"Tests failed:\n{output}",
                    confidence=0.0,
                    duration_ms=elapsed,
                    details=details,
                )

        except subprocess.TimeoutExpired:
            elapsed = int((time.monotonic() - start) * 1000)
            return CheckResult(
                check_name=self.name,
                passed=False,
                blocking_reason="Test suite gate timed out (45s limit)",
                confidence=0.0,
                duration_ms=elapsed,
                details=details,
            )
        finally:
            # Always restore original
            if backup_path.exists():
                os.replace(str(backup_path), str(file_path))

    def _find_relevant_tests(self, file_path: Path) -> List[Path]:
        """Find test files that import the module at file_path."""
        module_name = file_path.stem
        search_root = self.project_root or file_path.parent

        test_files: List[Path] = []
        for py_file in search_root.rglob("*.py"):
            name = py_file.name
            if not (name.startswith("test_") or name.endswith("_test.py")):
                continue
            if py_file == file_path:
                continue
            try:
                source = py_file.read_text(encoding="utf-8")
                if self._imports_module(source, module_name):
                    test_files.append(py_file)
            except Exception:
                continue
        return test_files

    @staticmethod
    def _imports_module(source: str, module_name: str) -> bool:
        """Check if source code imports the given module name."""
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return False

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == module_name or alias.name.startswith(module_name + "."):
                        return True
            elif isinstance(node, ast.ImportFrom):
                if node.module and (
                    node.module == module_name or node.module.startswith(module_name + ".")
                ):
                    return True
        return False

    @staticmethod
    def _clear_pycache(file_path: Path) -> None:
        """Remove .pyc files for this module to force re-import."""
        pycache = file_path.parent / "__pycache__"
        if pycache.exists():
            stem = file_path.stem
            for pyc in pycache.glob(f"{stem}.cpython-*.pyc"):
                try:
                    pyc.unlink()
                except Exception:
                    pass
