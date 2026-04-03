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
