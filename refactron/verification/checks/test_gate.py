import ast
from pathlib import Path
from typing import Dict, List, Optional

# Global cache for module -> relevant tests mapping
# Structure: {project_root_str: {target_module: [test_paths]}}
_TEST_DISCOVERY_CACHE: Dict[str, Dict[str, List[Path]]] = {}


class TestSuiteGate:
    def __init__(self, search_root: Path, project_root: Optional[Path] = None):
        self.search_root = search_root
        self.project_root = project_root

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
        
        # Check cache
        if cache_key in _TEST_DISCOVERY_CACHE and target_module in _TEST_DISCOVERY_CACHE[cache_key]:
            return _TEST_DISCOVERY_CACHE[cache_key][target_module]
            
        relevant_tests = []
        ignore_patterns = {"venv", ".venv", "site-packages", "node_modules", ".git", ".tox", ".pytest_cache", "__pycache__"}
        
        for p in self.search_root.rglob("*.py"):
            # Skip obvious non-target paths if project_root is set
            if self.project_root:
                # Check if any parent directory is in the ignore list
                if any(part in ignore_patterns for part in p.parts):
                    continue
                    
            if p.is_file() and p.name.startswith("test_"):
                if self._imports_module(p, target_module):
                    relevant_tests.append(p)
                    
        # Update cache
        if cache_key not in _TEST_DISCOVERY_CACHE:
            _TEST_DISCOVERY_CACHE[cache_key] = {}
            
        _TEST_DISCOVERY_CACHE[cache_key][target_module] = relevant_tests
        return relevant_tests
