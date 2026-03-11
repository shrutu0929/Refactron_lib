import ast
import sys

files = [
    r"c:\Users\Shruti kulkarni\Downloads\Refactron_lib\refactron\rag\parser.py",
    r"c:\Users\Shruti kulkarni\Downloads\Refactron_lib\refactron\rag\indexer.py"
]

for f_path in files:
    print(f"Checking {f_path}...")
    try:
        with open(f_path, "rb") as f:
            content = f.read()
            # Look for non-ascii or weird bytes
            non_ascii = [(i, b) for i, b in enumerate(content) if b > 127]
            if non_ascii:
                print(f"  Found {len(non_ascii)} non-ASCII bytes. First few: {non_ascii[:5]}")
            
            ast.parse(content)
            print("  AST parse: SUCCESS")
            
            # Search for the string the user is seeing
            if b"PY_LANGUAGE" in content:
                print("  CRITICAL: Found 'PY_LANGUAGE' in file despite overwrite!")
            else:
                print("  'PY_LANGUAGE' not found.")
                
    except Exception as e:
        print(f"  ERROR: {e}")
        import traceback
        traceback.print_exc()
    print("-" * 20)
