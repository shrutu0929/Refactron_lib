"""
Inference engine wrapping astroid for semantic analysis.
Provides capabilities to infer types, values, and resolve symbols.
"""

import os
from pathlib import Path
from typing import Any, List, Optional

import astroid
from astroid import nodes
from astroid.context import InferenceContext
from astroid.exceptions import InferenceError


class InferenceEngine:
    """
    Wrapper around astroid to provide high-level semantic analysis capabilities.
    """

    @staticmethod
    def parse_string(code: str, module_name: str = "") -> nodes.Module:
        """Parse source code string into an astroid node tree."""
        try:
            return astroid.parse(code, module_name=module_name)
        except Exception as e:
            # Fallback or re-raise with better context if needed
            raise ValueError(f"Failed to parse code with astroid: {e}")

    @staticmethod
    def parse_file(file_path: str) -> nodes.Module:
        """Parse a file into an astroid node tree."""
        # Use canonical path (resolved and posix-style for consistency)
        abs_path = Path(file_path).resolve().as_posix()
        manager = astroid.MANAGER

        # Aggressively clear cache for this file to ensure fresh AST
        # Try both resolved and absolute paths to handle symlinks and normalization differences
        raw_abs = os.path.abspath(file_path)
        manager.astroid_cache.pop(abs_path, None)
        manager.astroid_cache.pop(raw_abs, None)
        manager.astroid_cache.pop(file_path, None)

        # 2. Find and clear by module name if it exists in caches
        file_to_mod = getattr(manager, "file_to_module_cache", {})
        # Some versions use _mod_file_cache
        if not file_to_mod:
            file_to_mod = getattr(manager, "_mod_file_cache", {})

        modname = (
            file_to_mod.get(abs_path) or file_to_mod.get(raw_abs) or file_to_mod.get(file_path)
        )
        if modname:
            manager.astroid_cache.pop(modname, None)

        # 3. Exhaustive search in astroid_cache for any module pointing to this file
        for key, val in list(manager.astroid_cache.items()):
            if hasattr(val, "file") and val.file:
                val_path = Path(val.file).resolve().as_posix()
                if val_path == abs_path or val_path == raw_abs.replace("\\", "/"):
                    manager.astroid_cache.pop(key, None)

        # 4. Clear the mappings themselves
        for attr in ("file_to_module_cache", "_mod_file_cache"):
            cache = getattr(manager, attr, None)
            if isinstance(cache, dict):
                cache.pop(abs_path, None)
                cache.pop(raw_abs, None)
                cache.pop(file_path, None)

        # 5. Read file and parse directly to bypass astroid's file cache
        try:
            with open(abs_path, "r", encoding="utf-8") as f:
                code = f.read()

            # Resolve module name to keep astroid's state consistent
            modname = ""
            try:
                from astroid import modutils

                modname = modutils.modname_from_path(abs_path)
            except Exception:
                pass

            # Use string_build via parse to avoid manager.ast_from_file's internal caching
            return astroid.parse(code, module_name=modname, path=abs_path)
        except (OSError, UnicodeDecodeError):
            # Fallback to manager if manual read fails
            try:
                return manager.ast_from_file(abs_path)
            except Exception as e:
                # Fallback for virtual/non-existent files if needed
                raise ValueError(f"Failed to parse {abs_path}: {e}")

    @staticmethod
    def infer_node(node: nodes.NodeNG, context: Optional[InferenceContext] = None) -> List[Any]:
        """
        Attempt to infer the value/type of a given node.
        Returns a list of potential values (astroid nodes).
        """
        try:
            return list(node.infer(context=context))
        except InferenceError:
            return []

    @staticmethod
    def get_node_type_name(node: nodes.NodeNG) -> str:
        """Get the string representation of the inferred type."""
        inferred = InferenceEngine.infer_node(node)
        if not inferred:
            return "Uninferred"

        # Simple heuristic: take the first inference result
        obj = inferred[0]
        if isinstance(obj, nodes.Const):
            return type(obj.value).__name__
        if isinstance(obj, nodes.ClassDef):
            return str(obj.name)
        if isinstance(obj, nodes.FunctionDef):
            return "function"
        if isinstance(obj, nodes.Module):
            return "module"
        if obj is astroid.Uninferable:
            return "Uninferred"

        return str(getattr(obj, "name", str(type(obj))))

    @staticmethod
    def is_subtype_of(node: nodes.NodeNG, type_name: str) -> bool:
        """Check if node infers to a specific type name (e.g. 'str', 'int', 'MyClass')."""
        inferred_list = InferenceEngine.infer_node(node)
        for obj in inferred_list:
            if obj is astroid.Uninferable:
                continue

            # Check direct type name
            if getattr(obj, "name", "") == type_name:
                return True

            # Check instance class
            if isinstance(obj, nodes.Instance):
                if obj.name == type_name:
                    return True
                # Check ancestry
                for ancestor in obj.ancestors():
                    if ancestor.name == type_name:
                        return True

        return False
