import sys
from pathlib import Path

def test_ts():
    print("Testing Tree-Sitter types and results...")
    try:
        from tree_sitter import Language, Parser
        import tree_sitter_python as tspython
        
        lang_data = tspython.language()
        print(f"lang_data type: {type(lang_data)}")
        
        # Test Language class/function
        print(f"Language is: {Language}")
        
        lang_obj = Language(lang_data)
        print(f"Language(lang_data) type: {type(lang_obj)}")
        
        try:
            p = Parser(lang_obj)
            print("Parser(lang_obj) succeeded.")
        except Exception as e:
            print(f"Parser(lang_obj) failed: {type(e).__name__}: {e}")
            
    except Exception as e:
        print(f"Critical failure: {type(e).__name__}: {e}")

if __name__ == "__main__":
    test_ts()
