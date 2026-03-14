import sys
from pathlib import Path
import traceback

def verify():
    print("Verifying CodeParser initialization with robust Tree-Sitter logic...")
    try:
        from refactron.rag.parser import CodeParser
        
        parser = CodeParser()
        print("1. CodeParser initialized.")
        
        tree = parser.parser.parse(b"def hello(): pass\n")
        if tree and tree.root_node:
            print("2. Basic parsing verified.")
        else:
            print("2. Parsing failed to return tree.")
            sys.exit(1)
            
    except Exception as e:
        print(f"FAILED: {type(e).__name__}: {e}")
        traceback.print_exc()
        sys.exit(1)
    except BaseException as e:
        print(f"CRITICAL CRASH: {type(e).__name__}: {e}")
        sys.exit(1)

if __name__ == "__main__":
    verify()
    print("Verification finished.")
