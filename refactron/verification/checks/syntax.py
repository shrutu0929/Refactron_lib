import ast
from typing import Optional
from refactron.verification.engine import BaseCheck, VerificationContext

class SyntaxVerifier(BaseCheck):
    def verify(self, original: str, transformed: str, context: Optional[VerificationContext] = None) -> bool:
        """
        Verify the syntax of the transformed code.
        Uses shared VerificationContext to avoid redundant AST parsing.
        """
        # If the VerificationEngine already tried to parse it and failed, the syntax implies it's broken
        if context and context.transformed_ast is None and transformed.strip() != "":
            return False
            
        # Optional: libcst parsing could also be cached, but for now we fallback 
        # or rely strictly on ast if libcst isn't required by the context immediately
        
        # Fallback to local parsing for backward compatibility 
        # (e.g. if run independently without the pre-configured context)
        if not context:
            try:
                ast.parse(transformed)
            except Exception:
                return False
                
        return True
