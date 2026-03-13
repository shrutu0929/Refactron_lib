"""Code parser using tree-sitter for AST-aware code analysis."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, List, Optional, Tuple, cast

try:
    import tree_sitter_python as tspython
    from tree_sitter import Language, Node, Parser

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    # Use different names for mypy to avoid redefinition errors
    Language = Any  # type: ignore
    Node = Any  # type: ignore
    Parser = Any  # type: ignore
    tspython = None  # type: ignore

if TYPE_CHECKING:
    from tree_sitter import Language, Node, Parser


@dataclass
class ParsedFunction:
    """Represents a parsed function."""

    name: str
    body: str
    docstring: Optional[str]
    line_range: Tuple[int, int]
    params: List[str]


@dataclass
class ParsedClass:
    """Represents a parsed class."""

    name: str
    body: str
    docstring: Optional[str]
    line_range: Tuple[int, int]
    methods: List[ParsedFunction]


@dataclass
class ParsedFile:
    """Represents a parsed Python file."""

    file_path: str
    imports: List[str]
    functions: List[ParsedFunction]
    classes: List[ParsedClass]
    module_docstring: Optional[str]


class CodeParser:
    """AST-aware code parser using tree-sitter."""

    def __init__(self) -> None:
        """Initialize the parser with cross-version tree-sitter compatibility."""
        if not TREE_SITTER_AVAILABLE:
            raise RuntimeError(
                "tree-sitter is not available. Install with: "
                "pip install tree-sitter tree-sitter-python"
            )

        self.parser, self.language = self._init_parser()

    @staticmethod
    def _try_parse(parser: "Parser") -> bool:
        """Return True if this parser instance can actually parse Python code."""
        try:
            tree = parser.parse(b"x = 1\n")
            return tree is not None and tree.root_node is not None
        except Exception:
            return False

    @staticmethod
    def _init_parser() -> Tuple["Parser", "Language"]:
        """
        Initialize the tree-sitter parser with a strategy that supports multiple 
        versions and platforms, with special guards for Windows DLL stability.
        """
        if not tspython or not TREE_SITTER_AVAILABLE:
            raise RuntimeError("tree-sitter or tree-sitter-python is not installed.")

        import platform
        is_windows = platform.system() == "Windows"

        # 1. Get the language data capsule/object
        lang_data = None
        for attr in ["language", "get_language", "language_python"]:
            func = getattr(tspython, attr, None)
            if callable(func):
                try:
                    lang_data = func()
                    if lang_data:
                        break
                except BaseException:
                    continue

        if not lang_data:
            # ONLY attempt legacy file loading if NOT on Windows OR if it's the only option.
            # On Windows, this is more likely to cause DLL crashes than a simple RuntimeError.
            lib_path = getattr(tspython, "language_python", None) or getattr(tspython, "__file__", None)
            if isinstance(lib_path, str) and not lib_path.endswith("__init__.py"):
                if not is_windows:
                    lang_data = lib_path

        if not lang_data:
            raise RuntimeError("Could not find suitable language data in tree-sitter-python.")

        errors = []

        # Strategy 1: Modern API (Parser constructor)
        # This is the safest on modern tree-sitter (0.22+).
        try:
            # Most modern versions accept the capsule/Language object directly
            p = Parser(lang_data)  # type: ignore
            if CodeParser._try_parse(p):
                return p, cast(Language, lang_data)
        except BaseException as e:
            errors.append(f"Direct Parser(lang_data) failed: {type(e).__name__}")

        # Strategy 2: Language object wrapper (Modern)
        try:
            # Language(lang_data) with 1 arg is the modern way to wrap a capsule.
            lang_obj = lang_data if isinstance(lang_data, Language) else Language(lang_data)
            p = Parser(lang_obj)
            if CodeParser._try_parse(p):
                return p, lang_obj
            
            # Some versions might require set_language
            p = Parser()
            p.set_language(lang_obj)  # type: ignore
            if CodeParser._try_parse(p):
                return p, lang_obj
        except BaseException as e:
            errors.append(f"Modern Language wrapping failed: {type(e).__name__}")

        # Strategy 3: Legacy API (Language constructor with 2 arguments)
        # ONLY try this as a last resort on non-Windows systems.
        # On Windows, passing 2 args to modern tree-sitter can trigger OSError(22).
        if not is_windows and not isinstance(lang_data, Language):
            try:
                # This is the old 0.20-0.21 way: Language(path_or_capsule, "python")
                lang_obj = Language(lang_data, "python")  # type: ignore
                p = Parser()
                p.set_language(lang_obj)  # type: ignore
                if CodeParser._try_parse(p):
                    return p, lang_obj
            except BaseException as e:
                errors.append(f"Legacy 2-arg Language failed: {type(e).__name__}")

        # Strategy 4: Direct capsule to set_language
        try:
            p = Parser()
            p.set_language(lang_data)  # type: ignore
            if CodeParser._try_parse(p):
                return p, cast(Language, lang_data)
        except BaseException as e:
            errors.append(f"Direct set_language failed: {type(e).__name__}")

        raise RuntimeError(
            f"Could not initialize tree-sitter parser for Python. "
            f"Please check your installation. Details: {'; '.join(errors)}"
        )

    def parse_file(self, file_path: Path) -> ParsedFile:
        """Parse a Python file.

        Args:
            file_path: Path to the Python file

        Returns:
            ParsedFile object containing all parsed elements
        """
        with open(file_path, "rb") as f:
            source_code = f.read()

        tree = self.parser.parse(source_code)
        root = tree.root_node

        # Extract module docstring
        module_docstring = self._extract_module_docstring(root, source_code)

        # Extract imports
        imports = self._extract_imports(root, source_code)

        # Extract functions
        functions = self._extract_functions(root, source_code)

        # Extract classes
        classes = self._extract_classes(root, source_code)

        return ParsedFile(
            file_path=str(file_path),
            imports=imports,
            functions=functions,
            classes=classes,
            module_docstring=module_docstring,
        )

    def _extract_module_docstring(self, root: Node, source: bytes) -> Optional[str]:
        """Extract module-level docstring."""
        for child in root.children:
            if child.type == "expression_statement":
                string_node = child.children[0] if child.children else None
                if string_node and string_node.type == "string":
                    return (
                        source[string_node.start_byte : string_node.end_byte]
                        .decode("utf-8")
                        .strip("\"'")
                    )
        return None

    def _extract_imports(self, root: Node, source: bytes) -> List[str]:
        """Extract import statements."""
        imports = []
        for node in root.children:
            if node.type in ("import_statement", "import_from_statement"):
                # type: ignore
                import_text = source[node.start_byte : node.end_byte].decode("utf-8")
                imports.append(import_text)
        return imports

    def _extract_functions(self, root: Node, source: bytes) -> List[ParsedFunction]:
        """Extract function definitions."""
        functions = []
        for node in root.children:
            if node.type in ("function_definition", "async_function_definition"):
                func = self._parse_function(node, source)
                if func:
                    functions.append(func)
        return functions

    def _extract_classes(self, root: Node, source: bytes) -> List[ParsedClass]:
        """Extract class definitions."""
        classes = []
        for node in root.children:
            if node.type == "class_definition":
                cls = self._parse_class(node, source)
                if cls:
                    classes.append(cls)
        return classes

    def _parse_function(self, node: Node, source: bytes) -> Optional[ParsedFunction]:
        """Parse a function node."""
        # Get function name
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        name = source[name_node.start_byte : name_node.end_byte].decode("utf-8")

        # Get function body
        body = source[node.start_byte : node.end_byte].decode("utf-8")

        # Get docstring
        docstring = self._extract_function_docstring(node, source)

        # Get line range
        line_range = (node.start_point[0] + 1, node.end_point[0] + 1)

        # Get parameters
        params = self._extract_parameters(node, source)

        return ParsedFunction(
            name=name,
            body=body,
            docstring=docstring,
            line_range=line_range,
            params=params,
        )

    def _parse_class(self, node: Node, source: bytes) -> Optional[ParsedClass]:
        """Parse a class node."""
        # Get class name
        name_node = node.child_by_field_name("name")
        if not name_node:
            return None

        name = source[name_node.start_byte : name_node.end_byte].decode("utf-8")

        # Get class body
        body = source[node.start_byte : node.end_byte].decode("utf-8")

        # Get docstring
        docstring = self._extract_class_docstring(node, source)

        # Get line range
        line_range = (node.start_point[0] + 1, node.end_point[0] + 1)

        # Extract methods from class body
        methods = []
        body_node = node.child_by_field_name("body")
        if body_node:
            for child in body_node.children:
                if child.type in ("function_definition", "async_function_definition"):
                    method = self._parse_function(child, source)
                    if method:
                        methods.append(method)

        return ParsedClass(
            name=name,
            body=body,
            docstring=docstring,
            line_range=line_range,
            methods=methods,
        )

    def _extract_function_docstring(self, node: Node, source: bytes) -> Optional[str]:
        """Extract function docstring."""
        body_node = node.child_by_field_name("body")
        if not body_node:
            return None

        for child in body_node.children:
            if child.type == "expression_statement":
                string_node = child.children[0] if child.children else None
                if string_node and string_node.type == "string":
                    return (
                        source[string_node.start_byte : string_node.end_byte]
                        .decode("utf-8")
                        .strip("\"'")
                    )
        return None

    def _extract_class_docstring(self, node: Node, source: bytes) -> Optional[str]:
        """Extract class docstring."""
        body_node = node.child_by_field_name("body")
        if not body_node:
            return None

        for child in body_node.children:
            if child.type == "expression_statement":
                string_node = child.children[0] if child.children else None
                if string_node and string_node.type == "string":
                    return (
                        source[string_node.start_byte : string_node.end_byte]
                        .decode("utf-8")
                        .strip("\"'")
                    )
        return None

    def _extract_parameters(self, node: Node, source: bytes) -> List[str]:
        """Extract function parameters."""
        params: List[str] = []
        params_node = node.child_by_field_name("parameters")
        if not params_node:
            return params

        def get_param_name(n: Any) -> Optional[str]:
            # If it's an identifier, we found it
            if n.type == "identifier":
                return source[n.start_byte : n.end_byte].decode("utf-8")  # type: ignore

            # Check 'name' field first (standard for typed_parameter, default_parameter)
            name_node = n.child_by_field_name("name")
            if name_node:
                return get_param_name(name_node)

            # For splats (*args, **kwargs), the identifier is a child
            if n.type in ("list_splat_pattern", "dictionary_splat_pattern"):
                for child in n.named_children:
                    if child.type == "identifier":
                        # type: ignore
                        return source[child.start_byte : child.end_byte].decode("utf-8")

            # Fallback: first identifier child
            for child in n.named_children:
                if child.type == "identifier":
                    # type: ignore
                    return source[child.start_byte : child.end_byte].decode("utf-8")
            return None

        for child in params_node.named_children:
            # Skip punctuation/non-parameter nodes
            if child.type in ("(", ")", ","):
                continue

            name = get_param_name(child)
            if name:
                params.append(name)

        return params
