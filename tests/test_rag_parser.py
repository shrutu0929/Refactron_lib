"""Tests for the RAG parser module."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from refactron.rag.parser import (
    TREE_SITTER_AVAILABLE,
    CodeParser,
    ParsedClass,
    ParsedFile,
    ParsedFunction,
)


def _tree_sitter_usable() -> bool:
    if not TREE_SITTER_AVAILABLE:
        return False
    try:
        CodeParser()
        return True
    except RuntimeError:
        return False


pytestmark = pytest.mark.skipif(
    not _tree_sitter_usable(),
    reason="tree-sitter is not available or cannot be initialised in this environment",
)


class TestCodeParser:
    """Test cases for CodeParser."""

    @pytest.fixture
    def parser(self):
        """Create a CodeParser instance."""
        return CodeParser()

    @pytest.fixture
    def temp_python_file(self):
        """Create a temporary Python file for testing."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            content = '''"""Module docstring for testing."""

import os
import sys
from pathlib import Path

def simple_function(x, y):
    """Add two numbers."""
    return x + y

def another_function():
    """Function without params."""
    pass

class TestClass:
    """A test class."""

    def method_one(self):
        """First method."""
        return 1

    def method_two(self, param):
        """Second method."""
        return param * 2
'''
            f.write(content)
            temp_path = Path(f.name)

        yield temp_path

        # Cleanup
        temp_path.unlink()

    def test_parser_initialization(self, parser):
        """Test that parser initializes correctly."""
        assert parser is not None
        assert parser.parser is not None

    def test_parse_file_basic(self, parser, temp_python_file):
        """Test parsing a basic Python file."""
        parsed = parser.parse_file(temp_python_file)

        assert isinstance(parsed, ParsedFile)
        assert parsed.file_path == str(temp_python_file)
        assert parsed.module_docstring == "Module docstring for testing."

    def test_extract_imports(self, parser, temp_python_file):
        """Test that imports are extracted correctly."""
        parsed = parser.parse_file(temp_python_file)

        assert len(parsed.imports) == 3
        assert "import os" in parsed.imports
        assert "import sys" in parsed.imports
        assert any("pathlib" in imp for imp in parsed.imports)

    def test_extract_functions(self, parser, temp_python_file):
        """Test that functions are extracted correctly."""
        parsed = parser.parse_file(temp_python_file)

        assert len(parsed.functions) == 2

        # Check first function
        func1 = parsed.functions[0]
        assert isinstance(func1, ParsedFunction)
        assert func1.name == "simple_function"
        assert func1.docstring == "Add two numbers."
        assert len(func1.params) >= 2  # Should have x and y

        # Check second function
        func2 = parsed.functions[1]
        assert func2.name == "another_function"

    def test_extract_classes(self, parser, temp_python_file):
        """Test that classes are extracted correctly."""
        parsed = parser.parse_file(temp_python_file)

        assert len(parsed.classes) == 1

        # Check class
        cls = parsed.classes[0]
        assert isinstance(cls, ParsedClass)
        assert cls.name == "TestClass"
        assert cls.docstring == "A test class."

        # Check methods
        assert len(cls.methods) == 2
        assert cls.methods[0].name == "method_one"
        assert cls.methods[1].name == "method_two"

    def test_parse_invalid_file(self, parser):
        """Test parsing a non-existent file raises error."""
        with pytest.raises(FileNotFoundError):
            parser.parse_file(Path("/nonexistent/file.py"))

    def test_parse_empty_file(self, parser):
        """Test parsing an empty Python file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write("")
            temp_path = Path(f.name)

        try:
            parsed = parser.parse_file(temp_path)
            assert parsed.module_docstring is None
            assert len(parsed.imports) == 0
            assert len(parsed.functions) == 0
            assert len(parsed.classes) == 0
        finally:
            temp_path.unlink()

    def test_function_line_ranges(self, parser, temp_python_file):
        """Test that line ranges are captured correctly."""
        parsed = parser.parse_file(temp_python_file)

        for func in parsed.functions:
            assert func.line_range[0] > 0
            assert func.line_range[1] >= func.line_range[0]

    def test_class_methods_have_correct_metadata(self, parser, temp_python_file):
        """Test that class methods preserve metadata."""
        parsed = parser.parse_file(temp_python_file)

        test_class = parsed.classes[0]
        for method in test_class.methods:
            assert method.name in ["method_one", "method_two"]
            assert method.docstring is not None
            assert len(method.body) > 0


# ─────────────── RAG Parser (boost) ───────────────


class TestParsedDataclasses:
    def test_parsed_function_fields(self):
        from refactron.rag.parser import ParsedFunction

        f = ParsedFunction(
            name="foo", body="def foo(): pass", docstring=None, line_range=(1, 1), params=["x"]
        )
        assert f.name == "foo"

    def test_parsed_class_fields(self):
        from refactron.rag.parser import ParsedClass

        c = ParsedClass(
            name="MyClass",
            body="class MyClass: pass",
            docstring="A class",
            line_range=(1, 5),
            methods=[],
        )
        assert c.name == "MyClass"

    def test_parsed_file_fields(self):
        from refactron.rag.parser import ParsedFile

        f = ParsedFile(
            file_path="a.py",
            imports=["import os"],
            functions=[],
            classes=[],
            module_docstring="Module docs",
        )
        assert f.file_path == "a.py"


class TestCodeParserUnavailable:
    def test_raises_when_tree_sitter_unavailable(self):
        with patch("refactron.rag.parser.TREE_SITTER_AVAILABLE", False):
            import refactron.rag.parser as parser_mod

            with patch.object(parser_mod, "TREE_SITTER_AVAILABLE", False):
                with pytest.raises(RuntimeError, match="tree-sitter"):
                    parser_mod.CodeParser()


class TestCodeParserAvailable:
    @pytest.fixture()
    def parser(self):
        pytest.importorskip("tree_sitter")
        pytest.importorskip("tree_sitter_python")
        from refactron.rag.parser import CodeParser

        return CodeParser()

    def test_parse_simple_function(self, parser, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("def hello(x, y):\n    '''Say hello.'''\n    return x + y\n")
        result = parser.parse_file(f)
        assert result.file_path == str(f)
        func_names = [fn.name for fn in result.functions]
        assert "hello" in func_names

    def test_parse_function_params(self, parser, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("def greet(name, greeting='Hi'):\n    pass\n")
        result = parser.parse_file(f)
        fn = result.functions[0]
        assert "name" in fn.params

    def test_parse_class(self, parser, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("class Foo:\n    def bar(self):\n        pass\n")
        result = parser.parse_file(f)
        assert len(result.classes) == 1
        assert result.classes[0].name == "Foo"
        assert len(result.classes[0].methods) == 1

    def test_parse_imports(self, parser, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("import os\nfrom pathlib import Path\n\nx = 1\n")
        result = parser.parse_file(f)
        assert len(result.imports) == 2

    def test_parse_module_docstring(self, parser, tmp_path):
        f = tmp_path / "test.py"
        f.write_text('"""Module docstring."""\n\nx = 1\n')
        result = parser.parse_file(f)
        assert result.module_docstring is not None

    def test_parse_function_docstring(self, parser, tmp_path):
        f = tmp_path / "test.py"
        f.write_text('def foo():\n    """Foo docs."""\n    pass\n')
        result = parser.parse_file(f)
        assert result.functions[0].docstring is not None

    def test_parse_class_docstring(self, parser, tmp_path):
        f = tmp_path / "test.py"
        f.write_text('class Bar:\n    """Bar docs."""\n    pass\n')
        result = parser.parse_file(f)
        assert result.classes[0].docstring is not None

    def test_parse_empty_file(self, parser, tmp_path):
        f = tmp_path / "empty.py"
        f.write_text("")
        result = parser.parse_file(f)
        assert result.functions == [] and result.classes == []

    def test_parse_no_docstring(self, parser, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("def no_doc():\n    return 1\n")
        result = parser.parse_file(f)
        assert result.functions[0].docstring is None

    def test_parse_class_no_docstring(self, parser, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("class Bare:\n    pass\n")
        result = parser.parse_file(f)
        assert result.classes[0].docstring is None

    def test_line_range(self, parser, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("def foo():\n    x = 1\n    return x\n")
        result = parser.parse_file(f)
        assert result.functions[0].line_range[0] == 1

    def test_parse_nested_class_methods(self, parser, tmp_path):
        f = tmp_path / "test.py"
        code = "class A:\n    def m1(self): pass\n    def m2(self): pass\n"
        f.write_text(code)
        result = parser.parse_file(f)
        assert len(result.classes[0].methods) == 2


class TestCodeParserTreeSitterVersion:
    def test_minor_version_fallback(self):
        with patch("refactron.rag.parser.TREE_SITTER_AVAILABLE", True):
            # Just test it doesn't raise
            from refactron.rag.parser import CodeParser

            v = CodeParser._tree_sitter_minor_version()
            assert isinstance(v, int)

    def test_parser_works_valid(self):
        pytest.importorskip("tree_sitter")
        from refactron.rag.parser import CodeParser

        mock_parser = MagicMock()
        mock_parser.parse.return_value = MagicMock()  # Non-None
        assert CodeParser._parser_works(mock_parser) is True

    def test_parser_works_returns_none(self):
        pytest.importorskip("tree_sitter")
        from refactron.rag.parser import CodeParser

        mock_parser = MagicMock()
        mock_parser.parse.return_value = None
        assert CodeParser._parser_works(mock_parser) is False

    def test_parser_works_raises(self):
        pytest.importorskip("tree_sitter")
        from refactron.rag.parser import CodeParser

        mock_parser = MagicMock()
        mock_parser.parse.side_effect = Exception("parse error")
        assert CodeParser._parser_works(mock_parser) is False
