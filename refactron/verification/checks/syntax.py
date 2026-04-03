import ast
from typing import Optional
from refactron.verification.engine import BaseCheck, VerificationContext

# Module-level cache for lazy libcst loading
_libcst_module = None

def _get_libcst():
    global _libcst_module
    if _libcst_module is None:
        import libcst as cst
        _libcst_module = cst
    return _libcst_module


class SyntaxVerifier(BaseCheck):
    def _find_dangerous_calls(self, tree: ast.AST) -> int:
        dangerous_calls = {"eval", "exec", "system", "popen"}
        count = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in dangerous_calls:
                    count += 1
                elif isinstance(node.func, ast.Attribute) and node.func.attr in dangerous_calls:
                    count += 1
        return count

    def _count_imports(self, tree: ast.AST) -> int:
        count = 0
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                count += 1
        return count

    def verify(self, original: str, transformed: str, context: Optional[VerificationContext] = None) -> bool:
        """
        Verify the syntax of the transformed code.
        Uses shared VerificationContext to avoid redundant AST parsing.
        """
        # If the VerificationEngine already tried to parse it and failed, the syntax implies it's broken
        if context and context.transformed_ast is None and transformed.strip() != "":
            return False
            
        tree = context.transformed_ast if context else None
        
        # Fallback to local parsing for backward compatibility 
        if tree is None:
            try:
                tree = ast.parse(transformed)
            except Exception:
                return False

        # Reuse the single AST for analytical sweeps to save redundant walks
        dangerous = self._find_dangerous_calls(tree)
        if dangerous > 0:
            return False  # Abort on dangerous structural patterns
            
        _ = self._count_imports(tree)
            
        # Optional: libcst parsing could also be cached, but for now we fallback 
        # Lazy libcst loading significantly speeds up the hot loop.
        cst = _get_libcst()
        try:
            cst.parse_module(transformed)
        except Exception:
            return False
                
        return True
