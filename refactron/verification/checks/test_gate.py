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
