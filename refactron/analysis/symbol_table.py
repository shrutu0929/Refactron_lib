"""
Symbol Table implementation for semantic analysis.
Maps classes, functions, variables, and their relationships across the codebase.
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from refactron.core.inference import InferenceEngine

logger = logging.getLogger(__name__)


class SymbolType(str, Enum):
    CLASS = "class"
    FUNCTION = "function"
    VARIABLE = "variable"
    MODULE = "module"
    IMPORT = "import"


@dataclass
class Symbol:
    name: str
    type: SymbolType
    file_path: str
    line_number: int
    scope: str  # "global", "class:ClassName", "function:func_name"
    definition_node: Any = field(default=None, repr=False)  # AST/Astroid node
    references: List[tuple] = field(default_factory=list)  # List of (file_path, line_number)

    # Type inference data
    inferred_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize for caching (excluding the definition node)."""
        return {
            "name": self.name,
            "type": self.type.value,
            "file_path": self.file_path,
            "line_number": self.line_number,
            "scope": self.scope,
            "references": self.references,
            "inferred_type": self.inferred_type,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Symbol":
        """Deserialize from dictionary."""
        data["type"] = SymbolType(data["type"])
        return cls(**data)


@dataclass
class SymbolTable:
    # Map: file_path -> { scope -> { name -> Symbol } }
    symbols: Dict[str, Dict[str, Dict[str, Symbol]]] = field(default_factory=dict)
    # Map: global_name -> Symbol (for easy cross-file lookup of exports)
    exports: Dict[str, Symbol] = field(default_factory=dict)
    # Map: file_path -> { "mtime": float, "size": int, "sha256": str }
    file_metadata: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    @staticmethod
    def _normalize_path(path: str) -> str:
        """Standardize path format for consistent keys/storage."""
        return Path(path).resolve().as_posix()

    def add_symbol(self, symbol: Symbol) -> None:
        """Add a symbol to the table."""
        path = self._normalize_path(symbol.file_path)
        # Ensure the symbol itself stores the normalized path
        symbol.file_path = path

        if path not in self.symbols:
            self.symbols[path] = {}

        if symbol.scope not in self.symbols[path]:
            self.symbols[path][symbol.scope] = {}

        self.symbols[path][symbol.scope][symbol.name] = symbol

        # Track global exports (top-level functions and classes)
        if symbol.scope == "global" and symbol.type in (
            SymbolType.CLASS,
            SymbolType.FUNCTION,
            SymbolType.VARIABLE,
        ):
            self.exports[symbol.name] = symbol

    def remove_file(self, file_path: str) -> None:
        """Remove all symbols and metadata associated with a file."""
        norm_path = self._normalize_path(file_path)

        if norm_path in self.symbols:
            del self.symbols[norm_path]

        # Remove from exports
        names_to_remove = [
            name
            for name, sym in self.exports.items()
            if self._normalize_path(sym.file_path) == norm_path
        ]
        for name in names_to_remove:
            self.exports.pop(name, None)

        if norm_path in self.file_metadata:
            del self.file_metadata[norm_path]

    def get_symbol(self, file_path: str, name: str, scope: str = "global") -> Optional[Symbol]:
        """Retrieve a symbol."""
        norm_path = self._normalize_path(file_path)
        return self.symbols.get(norm_path, {}).get(scope, {}).get(name)

    def resolve_reference(
        self, name: str, current_file: str, current_scope: str
    ) -> Optional[Symbol]:
        """
        Attempt to resolve a name to a definition.
        1. Check local scope
        2. Check global scope of current file
        3. Check exports (cross-file)
        """
        # 1. Local scope
        local = self.get_symbol(current_file, name, current_scope)
        if local:
            return local

        # 2. File Global scope
        if current_scope != "global":
            file_global = self.get_symbol(current_file, name, "global")
            if file_global:
                return file_global

        # 3. Cross-file exports
        return self.exports.get(name)


class SymbolTableBuilder:
    """Builds and manages the project-wide symbol table."""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.symbol_table = SymbolTable()
        self.cache_dir = cache_dir
        self.inference_engine = InferenceEngine()

    def build_for_project(self, project_root: Path) -> SymbolTable:
        """Scan project and build symbol table incrementally."""
        if self.cache_dir:
            cached_table = self._load_cache()
            if cached_table:
                self.symbol_table = cached_table

        python_files = list(project_root.rglob("*.py"))
        current_file_paths = {fp.resolve().as_posix() for fp in python_files}

        # 1. Remove deleted files
        cached_files = list(self.symbol_table.file_metadata.keys())
        for cached_path in cached_files:
            if cached_path not in current_file_paths:
                logger.debug(f"Removing deleted file from symbol table: {cached_path}")
                self.symbol_table.remove_file(cached_path)

        # 2. Analyze new or modified files
        for file_path in python_files:
            abs_path = file_path.resolve()
            path_str = abs_path.as_posix()
            if self._has_file_changed(abs_path, path_str):
                logger.debug(f"Analyzing changed file: {path_str}")
                self.symbol_table.remove_file(path_str)
                self._analyze_file(abs_path)
                self._update_file_metadata(abs_path, path_str)

        if self.cache_dir:
            self._save_cache()

        return self.symbol_table

    def _has_file_changed(self, file_path: Path, file_path_str: str) -> bool:
        """Check if file has changed since last analysis."""
        if file_path_str not in self.symbol_table.file_metadata:
            return True

        metadata = self.symbol_table.file_metadata[file_path_str]
        try:
            stat = file_path.stat()
            if stat.st_size != metadata.get("size"):
                return True

            # Authoritative check: compare SHA-256 hashes
            stored_hash = metadata.get("sha256")
            if stored_hash:
                current_hash = self._calculate_hash(file_path)
                return current_hash != stored_hash

            return stat.st_mtime != metadata.get("mtime")
        except Exception:
            return True

    def _calculate_hash(self, file_path: Path) -> str:
        """Calculate SHA-256 hash of file content."""
        try:
            return hashlib.sha256(file_path.read_bytes()).hexdigest()
        except Exception:
            return ""

    def _update_file_metadata(self, file_path: Path, path_str: str) -> None:
        """Update file metadata in symbol table."""
        try:
            stat = file_path.stat()
            self.symbol_table.file_metadata[path_str] = {
                "mtime": stat.st_mtime,
                "size": stat.st_size,
                "sha256": self._calculate_hash(file_path),
            }
        except Exception as e:
            logger.warning(f"Failed to update metadata for {path_str}: {e}")

    def _analyze_file(self, file_path: Path) -> None:
        """Analyze a single file and populate symbols."""
        path_str = file_path.resolve().as_posix()
        try:
            tree = self.inference_engine.parse_file(path_str)
            self._visit_node(tree, path_str, "global")
        except Exception as e:
            logger.warning(f"Failed to build symbol table for {path_str}: {e}")

    def _visit_node(self, node: Any, file_path: str, scope: str) -> None:
        """Recursive node visitor."""
        import astroid.nodes as nodes

        new_scope = scope

        # Recognize both FunctionDef and AsyncFunctionDef
        if isinstance(node, (nodes.ClassDef, nodes.FunctionDef, nodes.AsyncFunctionDef)):
            symbol_type = (
                SymbolType.CLASS if isinstance(node, nodes.ClassDef) else SymbolType.FUNCTION
            )
            symbol = Symbol(
                name=node.name,
                type=symbol_type,
                file_path=file_path,
                line_number=node.lineno,
                scope=scope,
                definition_node=node,
            )
            self.symbol_table.add_symbol(symbol)

            # Enter new scope
            prefix = "class" if isinstance(node, nodes.ClassDef) else "function"
            new_scope = f"{prefix}:{node.name}"

        elif isinstance(node, nodes.AssignName):
            # Register variable assignment
            symbol = Symbol(
                name=node.name,
                type=SymbolType.VARIABLE,
                file_path=file_path,
                line_number=node.lineno,
                scope=scope,
                definition_node=node,
            )
            # Try to infer type
            try:
                symbol.inferred_type = self.inference_engine.get_node_type_name(node)
            except Exception:
                pass

            self.symbol_table.add_symbol(symbol)

        # Recurse children
        for child in node.get_children():
            self._visit_node(child, file_path, new_scope)

    def _save_cache(self) -> None:
        """Save symbol table to cache."""
        if not self.cache_dir:
            return

        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cache_file = self.cache_dir / "symbols.json"

            data = {
                "symbols": {
                    f: {
                        s: {n: sym.to_dict() for n, sym in names.items()}
                        for s, names in scopes.items()
                    }
                    for f, scopes in self.symbol_table.symbols.items()
                },
                "exports": {n: sym.to_dict() for n, sym in self.symbol_table.exports.items()},
                "file_metadata": self.symbol_table.file_metadata,
            }

            with open(cache_file, "w") as f:
                json.dump(data, f)
        except Exception as e:
            logger.warning(f"Failed to save symbol table cache: {e}")

    def _load_cache(self) -> Optional[SymbolTable]:
        """Load symbol table from cache."""
        if not self.cache_dir:
            return None

        cache_file = self.cache_dir / "symbols.json"
        if not cache_file.exists():
            return None

        try:
            with open(cache_file, "r") as f:
                data = json.load(f)

            table = SymbolTable()

            # Reconstruct symbols
            for f_path, scopes in data.get("symbols", {}).items():
                # Normalize path on load just in case
                norm_f_path = SymbolTable._normalize_path(f_path)
                table.symbols[norm_f_path] = {}
                for scope_name, names in scopes.items():
                    table.symbols[norm_f_path][scope_name] = {}
                    for name, sym_data in names.items():
                        sym = Symbol.from_dict(sym_data)
                        sym.file_path = norm_f_path
                        table.symbols[norm_f_path][scope_name][name] = sym

            # Reconstruct exports
            for name, sym_data in data.get("exports", {}).items():
                sym = Symbol.from_dict(sym_data)
                sym.file_path = SymbolTable._normalize_path(sym.file_path)
                table.exports[name] = sym

            # Reconstruct metadata
            file_metadata = data.get("file_metadata", {})
            table.file_metadata = {
                SymbolTable._normalize_path(k): v for k, v in file_metadata.items()
            }

            return table

        except Exception as e:
            logger.warning(f"Failed to load symbol table cache: {e}")
            return None
