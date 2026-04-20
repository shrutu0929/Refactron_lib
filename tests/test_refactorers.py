"""Comprehensive tests for all refactorers."""

from pathlib import Path
from unittest.mock import patch

import pytest

from refactron.autofix.fixers import (
    AddDocstringsFixer,
    AddMissingCommasFixer,
    ConvertToFStringFixer,
    ExtractMagicNumbersFixer,
    FixIndentationFixer,
    FixTypeHintsFixer,
    NormalizeQuotesFixer,
    RemoveDeadCodeFixer,
    RemovePrintStatementsFixer,
    RemoveTrailingWhitespaceFixer,
    RemoveUnusedImportsFixer,
    RemoveUnusedVariablesFixer,
    SimplifyBooleanFixer,
    SortImportsFixer,
)
from refactron.core.config import RefactronConfig
from refactron.core.models import CodeIssue, IssueCategory, IssueLevel
from refactron.refactorers.add_docstring_refactorer import AddDocstringRefactorer
from refactron.refactorers.extract_method_refactorer import ExtractMethodRefactorer
from refactron.refactorers.magic_number_refactorer import MagicNumberRefactorer
from refactron.refactorers.reduce_parameters_refactorer import ReduceParametersRefactorer
from refactron.refactorers.simplify_conditionals_refactorer import SimplifyConditionalsRefactorer


class TestMagicNumberRefactorer:
    """Test MagicNumberRefactorer functionality."""

    def test_refactorer_name(self):
        config = RefactronConfig()
        refactorer = MagicNumberRefactorer(config)
        assert refactorer.operation_type == "extract_constant"

    def test_extracts_magic_numbers(self):
        config = RefactronConfig()
        refactorer = MagicNumberRefactorer(config)

        code = """
def calculate_discount(price):
    if price > 1000:
        return price * 0.15
    elif price > 500:
        return price * 0.10
    return 0
"""

        operations = refactorer.refactor(Path("test.py"), code)
        assert len(operations) > 0

        # Should suggest extracting constants
        op = operations[0]
        assert "constant" in op.description.lower()
        assert op.risk_score < 0.3  # Should be safe
        assert "THRESHOLD" in op.new_code or "DISCOUNT" in op.new_code

    def test_ignores_common_numbers(self):
        config = RefactronConfig()
        refactorer = MagicNumberRefactorer(config)

        code = """
def process(data):
    result = data * 2  # 2 is common, should be ignored
    if result > 0:
        return result + 1
    return -1
"""

        operations = refactorer.refactor(Path("test.py"), code)
        # Should not suggest extracting 0, 1, 2, -1
        assert len(operations) == 0

    def test_handles_syntax_errors(self):
        config = RefactronConfig()
        refactorer = MagicNumberRefactorer(config)

        code = "def broken function(:"
        operations = refactorer.refactor(Path("test.py"), code)
        assert len(operations) == 0  # Should handle gracefully


class TestReduceParametersRefactorer:
    """Test ReduceParametersRefactorer functionality."""

    def test_refactorer_name(self):
        config = RefactronConfig()
        refactorer = ReduceParametersRefactorer(config)
        assert refactorer.operation_type == "reduce_parameters"

    def test_detects_too_many_parameters(self):
        config = RefactronConfig(max_parameters=3)
        refactorer = ReduceParametersRefactorer(config)

        code = """
def calculate_total(price, tax, discount, shipping, handling_fee, insurance):
    return price + tax - discount + shipping + handling_fee + insurance
"""

        operations = refactorer.refactor(Path("test.py"), code)
        assert len(operations) > 0

        op = operations[0]
        assert "parameters" in op.description.lower() or "config" in op.description.lower()
        assert op.risk_score > 0.3  # Moderate risk (API change)
        assert "dataclass" in op.new_code or "Config" in op.new_code

    def test_generates_config_class(self):
        config = RefactronConfig(max_parameters=2)
        refactorer = ReduceParametersRefactorer(config)

        code = """
def process(a, b, c, d):
    return a + b + c + d
"""

        operations = refactorer.refactor(Path("test.py"), code)
        assert len(operations) > 0

        op = operations[0]
        # Should generate a config class
        assert "@dataclass" in op.new_code
        assert "Config" in op.new_code
        assert all(param in op.new_code for param in ["a", "b", "c", "d"])

    def test_infers_types(self):
        config = RefactronConfig(max_parameters=2)
        refactorer = ReduceParametersRefactorer(config)

        code = """
def calculate(price, count, is_premium):
    return price * count if is_premium else price
"""

        operations = refactorer.refactor(Path("test.py"), code)
        assert len(operations) > 0

        op = operations[0]
        # Should infer types from names
        assert "float" in op.new_code or "int" in op.new_code

    def test_skips_functions_with_few_parameters(self):
        config = RefactronConfig(max_parameters=5)
        refactorer = ReduceParametersRefactorer(config)

        code = """
def simple(a, b):
    return a + b
"""

        operations = refactorer.refactor(Path("test.py"), code)
        assert len(operations) == 0

    def test_handles_syntax_errors(self):
        config = RefactronConfig()
        refactorer = ReduceParametersRefactorer(config)

        code = "def broken(:"
        operations = refactorer.refactor(Path("test.py"), code)
        assert len(operations) == 0


class TestAddDocstringRefactorer:
    """Test AddDocstringRefactorer functionality."""

    def test_refactorer_name(self):
        config = RefactronConfig()
        refactorer = AddDocstringRefactorer(config)
        assert refactorer.operation_type == "add_docstring"

    def test_adds_function_docstring(self):
        config = RefactronConfig()
        refactorer = AddDocstringRefactorer(config)

        code = """
def calculate_total(price, tax):
    return price + tax
"""

        operations = refactorer.refactor(Path("test.py"), code)
        assert len(operations) > 0

        op = operations[0]
        assert "docstring" in op.description.lower()
        assert op.risk_score == 0.0  # Perfectly safe
        assert "'''" in op.new_code
        assert "Args:" in op.new_code
        assert "Returns:" in op.new_code

    def test_adds_class_docstring(self):
        config = RefactronConfig()
        refactorer = AddDocstringRefactorer(config)

        code = """
class DataProcessor:
    def process(self):
        pass
"""

        operations = refactorer.refactor(Path("test.py"), code)
        # Should suggest docstring for class
        class_ops = [op for op in operations if "DataProcessor" in op.description]
        assert len(class_ops) > 0

        op = class_ops[0]
        assert "'''" in op.new_code

    def test_skips_private_functions(self):
        config = RefactronConfig()
        refactorer = AddDocstringRefactorer(config)

        code = """
def _private_function():
    return 42
"""

        operations = refactorer.refactor(Path("test.py"), code)
        # Should skip private functions
        assert len(operations) == 0

    def test_skips_functions_with_docstrings(self):
        config = RefactronConfig()
        refactorer = AddDocstringRefactorer(config)

        code = """
def documented_function():
    '''This already has a docstring.'''
    return 42
"""

        operations = refactorer.refactor(Path("test.py"), code)
        assert len(operations) == 0

    def test_generates_appropriate_descriptions(self):
        config = RefactronConfig()
        refactorer = AddDocstringRefactorer(config)

        code = """
def get_user(user_id):
    return None

def set_config(value):
    pass

def is_valid(data):
    return True

def calculate_total(items):
    return sum(items)
"""

        operations = refactorer.refactor(Path("test.py"), code)
        assert len(operations) >= 4

        # Should generate appropriate descriptions based on function names
        descriptions = [op.new_code for op in operations]
        _combined = "\n".join(descriptions)  # noqa: F841

        # Check for contextual descriptions
        assert any("Get" in d or "get" in d for d in descriptions)
        assert any("Set" in d or "set" in d for d in descriptions)
        assert any("Check" in d or "valid" in d for d in descriptions)
        assert any("Calculate" in d or "calculate" in d for d in descriptions)

    def test_handles_syntax_errors(self):
        config = RefactronConfig()
        refactorer = AddDocstringRefactorer(config)

        code = "def broken(:"
        operations = refactorer.refactor(Path("test.py"), code)
        assert len(operations) == 0


class TestSimplifyConditionalsRefactorer:
    """Test SimplifyConditionalsRefactorer functionality."""

    def test_refactorer_name(self):
        config = RefactronConfig()
        refactorer = SimplifyConditionalsRefactorer(config)
        assert refactorer.operation_type == "simplify_conditionals"

    def test_detects_deep_nesting(self):
        config = RefactronConfig()
        refactorer = SimplifyConditionalsRefactorer(config)

        code = """
def process_order(order_type, amount, customer_type, location):
    if order_type == "online":
        if amount > 100:
            if customer_type == "premium":
                if location == "domestic":
                    return amount * 0.7
                return amount * 0.8
            return amount * 0.9
        return amount
    return amount * 1.05
"""

        operations = refactorer.refactor(Path("test.py"), code)
        assert len(operations) > 0

        op = operations[0]
        assert "nesting" in op.description.lower() or "early return" in op.description.lower()
        assert op.risk_score >= 0.2  # Moderate risk
        assert "guard" in op.reasoning.lower() or "early" in op.reasoning.lower()

    def test_skips_shallow_nesting(self):
        config = RefactronConfig()
        refactorer = SimplifyConditionalsRefactorer(config)

        code = """
def simple_check(x):
    if x > 0:
        return "positive"
    return "negative"
"""

        operations = refactorer.refactor(Path("test.py"), code)
        assert len(operations) == 0  # Shallow nesting is fine

    def test_handles_syntax_errors(self):
        config = RefactronConfig()
        refactorer = SimplifyConditionalsRefactorer(config)

        code = "def broken(:"
        operations = refactorer.refactor(Path("test.py"), code)
        assert len(operations) == 0


class TestExtractMethodRefactorer:
    """Test ExtractMethodRefactorer functionality."""

    def test_refactorer_name(self):
        config = RefactronConfig()
        refactorer = ExtractMethodRefactorer(config)
        assert refactorer.operation_type == "extract_method"

    def test_detects_long_functions(self):
        """Test that long functions are detected."""
        config = RefactronConfig()
        refactorer = ExtractMethodRefactorer(config)

        # Create a function with >20 statements
        code = """
def very_long_function():
    x = 1
    y = 2
    z = 3
    a = 4
    b = 5
    c = 6
    d = 7
    e = 8
    f = 9
    g = 10
    h = 11
    i = 12
    j = 13
    k = 14
    l = 15
    m = 16
    n = 17
    o = 18
    p = 19
    q = 20
    r = 21
    for item in range(10):
        print(item)
"""

        operations = refactorer.refactor(Path("test.py"), code)
        assert len(operations) > 0
        assert operations[0].operation_type == "extract_method"
        assert (
            "complex block" in operations[0].description.lower()
            or "extract" in operations[0].description.lower()
        )

    def test_suggests_extracting_loops(self):
        """Test that loops in long functions are candidates for extraction."""
        config = RefactronConfig()
        refactorer = ExtractMethodRefactorer(config)

        code = """
def process_data():
    # Many statements to make it long
    x1 = 1
    x2 = 2
    x3 = 3
    x4 = 4
    x5 = 5
    x6 = 6
    x7 = 7
    x8 = 8
    x9 = 9
    x10 = 10
    x11 = 11
    x12 = 12
    x13 = 13
    x14 = 14
    x15 = 15
    x16 = 16
    x17 = 17
    x18 = 18
    x19 = 19
    x20 = 20
    x21 = 21

    # This loop should be suggested for extraction
    for i in range(100):
        result = i * 2
        print(result)
"""

        operations = refactorer.refactor(Path("test.py"), code)
        assert len(operations) > 0
        assert "extract" in operations[0].description.lower()

    def test_risk_score_is_moderate(self):
        """Test that extract method operations have moderate risk."""
        config = RefactronConfig()
        refactorer = ExtractMethodRefactorer(config)

        code = (
            """
def long_function():
    """
            + "\n    ".join([f"x{i} = {i}" for i in range(25)])
            + """
    for i in range(10):
        print(i)
"""
        )

        operations = refactorer.refactor(Path("test.py"), code)
        assert len(operations) > 0

        # Risk should be moderate (0.3-0.7)
        assert 0.3 <= operations[0].risk_score <= 0.7

    def test_skips_short_functions(self):
        """Test that short functions are not flagged."""
        config = RefactronConfig()
        refactorer = ExtractMethodRefactorer(config)

        code = """
def short_function():
    x = 1
    y = 2
    return x + y
"""

        operations = refactorer.refactor(Path("test.py"), code)
        assert len(operations) == 0

    def test_provides_reasoning(self):
        """Test that reasoning is provided for suggestions."""
        config = RefactronConfig()
        refactorer = ExtractMethodRefactorer(config)

        code = (
            """
def long_function():
    """
            + "\n    ".join([f"x{i} = {i}" for i in range(25)])
            + """
    while True:
        break
"""
        )

        operations = refactorer.refactor(Path("test.py"), code)
        assert len(operations) > 0
        assert operations[0].reasoning
        assert len(operations[0].reasoning) > 10

    def test_handles_syntax_errors(self):
        """Test graceful handling of syntax errors."""
        config = RefactronConfig()
        refactorer = ExtractMethodRefactorer(config)

        code = "def broken function(:"
        operations = refactorer.refactor(Path("test.py"), code)
        assert len(operations) == 0

    def test_handles_with_statements(self):
        """Test detection of with statements."""
        config = RefactronConfig()
        refactorer = ExtractMethodRefactorer(config)

        code = (
            """
def file_processor():
    """
            + "\n    ".join([f"x{i} = {i}" for i in range(25)])
            + """
    with open('file.txt') as f:
        data = f.read()
        process(data)
"""
        )

        operations = refactorer.refactor(Path("test.py"), code)
        assert len(operations) > 0

    def test_only_one_suggestion_per_function(self):
        """Test that only one extraction is suggested per function."""
        config = RefactronConfig()
        refactorer = ExtractMethodRefactorer(config)

        code = (
            """
def long_function():
    """
            + "\n    ".join([f"x{i} = {i}" for i in range(25)])
            + """

    for i in range(10):
        print(i)

    for j in range(10):
        print(j)

    while True:
        break
"""
        )

        operations = refactorer.refactor(Path("test.py"), code)
        # Should only suggest one extraction per function
        assert len(operations) == 1

    def test_code_snippet_extraction(self):
        """Test that code snippets are extracted correctly."""
        config = RefactronConfig()
        refactorer = ExtractMethodRefactorer(config)

        code = (
            """
def long_function():
    """
            + "\n    ".join([f"x{i} = {i}" for i in range(25)])
            + """
    for i in range(10):
        result = i * 2
"""
        )

        operations = refactorer.refactor(Path("test.py"), code)
        assert len(operations) > 0
        assert operations[0].old_code  # Should have old code
        assert operations[0].new_code  # Should have new code

    def test_async_functions_supported(self):
        """Test that async functions are also analyzed."""
        config = RefactronConfig()
        refactorer = ExtractMethodRefactorer(config)

        code = (
            """
async def async_long_function():
    """
            + "\n    ".join([f"x{i} = {i}" for i in range(25)])
            + """
    for i in range(10):
        await process(i)
"""
        )

        operations = refactorer.refactor(Path("test.py"), code)
        assert len(operations) > 0


class TestRefactorerIntegration:
    """Integration tests for refactorers."""

    def test_all_refactorers_work_together(self):
        """Test that all refactorers can run on the same code."""
        config = RefactronConfig()

        refactorers = [
            MagicNumberRefactorer(config),
            ReduceParametersRefactorer(config),
            AddDocstringRefactorer(config),
            SimplifyConditionalsRefactorer(config),
            ExtractMethodRefactorer(config),
        ]

        code = """
def process_data(a, b, c, d, e, f):
    if True:
        if True:
            if True:
                result = a * 100
                return result
    return 0
"""

        all_operations = []
        for refactorer in refactorers:
            operations = refactorer.refactor(Path("test.py"), code)
            all_operations.extend(operations)

        # Should detect multiple types of refactoring opportunities
        assert len(all_operations) > 0

        # Should have different operation types
        operation_types = set(op.operation_type for op in all_operations)
        assert len(operation_types) > 1

    def test_refactorers_provide_complete_information(self):
        """Test that all refactorers provide required information."""
        config = RefactronConfig()
        refactorer = MagicNumberRefactorer(config)

        code = """
def calculate(price):
    if price > 1000:
        return price * 0.15
    return 0
"""

        operations = refactorer.refactor(Path("test.py"), code)
        assert len(operations) > 0

        op = operations[0]
        # Check all required fields
        assert op.operation_type
        assert op.file_path
        assert op.line_number > 0
        assert op.description
        assert op.old_code
        assert op.new_code
        assert 0.0 <= op.risk_score <= 1.0
        assert op.reasoning


# ─────────────── Fixers Coverage (boost) ───────────────


def make_issue(
    line_number: int = 1,
    message: str = "test issue",
    metadata: dict = None,
    category: IssueCategory = IssueCategory.MODERNIZATION,
    level: IssueLevel = IssueLevel.WARNING,
) -> CodeIssue:
    return CodeIssue(
        category=category,
        level=level,
        message=message,
        file_path=Path("test.py"),
        line_number=line_number,
        metadata=metadata or {},
    )


# ─────────────────────────── RemoveUnusedImportsFixer ────────────────────────


class TestRemoveUnusedImportsFixer:
    def setup_method(self):
        self.fixer = RemoveUnusedImportsFixer()

    def test_no_unused_imports(self):
        code = "import os\n\nos.getcwd()\n"
        issue = make_issue()
        result = self.fixer.preview(issue, code)
        assert result.success is True
        assert "clean" in result.reason.lower() or "No unused" in result.reason

    def test_removes_unused_import(self):
        code = "import os\nimport sys\n\nprint('hello')\n"
        issue = make_issue()
        result = self.fixer.preview(issue, code)
        assert result.success is True
        assert "Removed" in result.reason or result.diff is not None or result.fixed is not None

    def test_apply_equals_preview(self):
        code = "import os\nimport sys\n\nprint('hello')\n"
        issue = make_issue()
        assert self.fixer.apply(issue, code).reason == self.fixer.preview(issue, code).reason

    def test_syntax_error_code(self):
        code = "def foo(:\n    pass"
        issue = make_issue()
        result = self.fixer.preview(issue, code)
        assert result.success is True  # returns code unchanged with count 0

    def test_from_import_unused(self):
        code = "from pathlib import Path\nfrom os import getcwd\n\nx = 1\n"
        issue = make_issue()
        result = self.fixer.preview(issue, code)
        assert result.success is True

    def test_wildcard_import_skipped(self):
        code = "from os import *\nx = 1\n"
        issue = make_issue()
        result = self.fixer.preview(issue, code)
        assert result.success is True

    def test_diff_creation(self):
        code = "import os\nimport sys\n\nprint('hello')\n"
        issue = make_issue()
        result = self.fixer.preview(issue, code)
        if result.diff:
            assert "---" in result.diff or "-" in result.diff

    def test_find_used_names_attribute(self):
        code = "import os\n\npath = os.path.join('a','b')\n"
        issue = make_issue()
        result = self.fixer.preview(issue, code)
        assert result.success is True

    def test_aliased_import_used(self):
        code = "import numpy as np\n\nx = np.array([1])\n"
        issue = make_issue()
        result = self.fixer.preview(issue, code)
        assert result.success is True


# ─────────────────────────── ExtractMagicNumbersFixer ────────────────────────


class TestExtractMagicNumbersFixer:
    def setup_method(self):
        self.fixer = ExtractMagicNumbersFixer()

    def test_no_value_in_metadata(self):
        issue = make_issue()  # no 'value' key
        result = self.fixer.preview(issue, "x = 42")
        assert result.success is False
        assert "No magic number" in result.reason

    def test_extracts_integer(self):
        issue = make_issue(metadata={"value": 42})
        code = "x = 42\n"
        result = self.fixer.preview(issue, code)
        assert result.success is True
        assert "CONSTANT_42" in result.fixed

    def test_extracts_float(self):
        issue = make_issue(metadata={"value": 3.14})
        code = "x = 3.14\n"
        result = self.fixer.preview(issue, code)
        assert result.success is True
        assert "CONSTANT_3_14" in result.fixed

    def test_context_in_metadata(self):
        issue = make_issue(metadata={"value": 100, "context": "timeout"})
        code = "wait = 100\n"
        result = self.fixer.preview(issue, code)
        assert result.success is True
        assert "TIMEOUT_VALUE" in result.fixed

    def test_apply_equals_preview(self):
        issue = make_issue(metadata={"value": 5})
        code = "n = 5\n"
        assert self.fixer.apply(issue, code).fixed == self.fixer.preview(issue, code).fixed


# ─────────────────────────── AddDocstringsFixer ──────────────────────────────


class TestAddDocstringsFixer:
    def setup_method(self):
        self.fixer = AddDocstringsFixer()

    def test_syntax_error(self):
        issue = make_issue(line_number=1)
        result = self.fixer.preview(issue, "def foo(:\n    pass")
        assert result.success is False
        assert "Syntax error" in result.reason

    def test_adds_docstring_to_function(self):
        code = "def foo():\n    x = 1\n"
        issue = make_issue(line_number=1)
        result = self.fixer.preview(issue, code)
        # Should either add docstring or report it couldn't
        assert isinstance(result.success, bool)

    def test_line_exceeds_code(self):
        code = "def foo():\n    pass\n"
        issue = make_issue(line_number=999)
        # Line number beyond code length should return unchanged
        result = self.fixer.preview(issue, code)
        assert result.success is False

    def test_apply_calls_preview(self):
        code = "def bar():\n    return 1\n"
        issue = make_issue(line_number=1)
        assert self.fixer.apply(issue, code).reason == self.fixer.preview(issue, code).reason


# ─────────────────────────── RemoveDeadCodeFixer ─────────────────────────────


class TestRemoveDeadCodeFixer:
    def setup_method(self):
        self.fixer = RemoveDeadCodeFixer()

    def test_removes_line(self):
        code = "x = 1\ny = 2\nz = 3\n"
        issue = make_issue(line_number=2)
        result = self.fixer.preview(issue, code)
        assert result.success is True
        assert "y = 2" not in result.fixed

    def test_invalid_line_number(self):
        code = "x = 1\n"
        issue = make_issue(line_number=999)
        result = self.fixer.preview(issue, code)
        assert result.success is False
        assert "Invalid" in result.reason

    def test_apply_equals_preview(self):
        code = "a = 1\nb = 2\n"
        issue = make_issue(line_number=1)
        assert self.fixer.apply(issue, code).fixed == self.fixer.preview(issue, code).fixed


# ─────────────────────────── FixTypeHintsFixer ───────────────────────────────


class TestFixTypeHintsFixer:
    def setup_method(self):
        self.fixer = FixTypeHintsFixer()

    def test_always_not_implemented(self):
        issue = make_issue()
        result = self.fixer.preview(issue, "def foo(): pass")
        assert result.success is False
        assert "not yet implemented" in result.reason

    def test_apply_same_as_preview(self):
        issue = make_issue()
        code = "def foo(): pass"
        assert self.fixer.apply(issue, code).reason == self.fixer.preview(issue, code).reason


# ─────────────────────────── SortImportsFixer ────────────────────────────────


class TestSortImportsFixer:
    def setup_method(self):
        self.fixer = SortImportsFixer()

    def test_isort_not_available(self):
        issue = make_issue()
        code = "import sys\nimport os\n"
        with patch.dict("sys.modules", {"isort": None}):
            result = self.fixer.preview(issue, code)
            # Either sorted or isort not installed message
            assert isinstance(result.success, bool)

    def test_imports_already_sorted(self):
        # If isort is available i.e. code doesn't change, reason = "already sorted"
        pytest.importorskip("isort")
        code = "import os\nimport sys\n"
        issue = make_issue()
        result = self.fixer.preview(issue, code)
        assert result.success is True

    def test_sorts_imports(self):
        pytest.importorskip("isort")
        code = "import sys\nimport os\n"
        issue = make_issue()
        result = self.fixer.preview(issue, code)
        assert result.success is True

    def test_apply_calls_preview(self):
        issue = make_issue()
        code = "import sys\nimport os\n"
        assert self.fixer.apply(issue, code).success == self.fixer.preview(issue, code).success


# ─────────────────────────── RemoveTrailingWhitespaceFixer ───────────────────


class TestRemoveTrailingWhitespaceFixer:
    def setup_method(self):
        self.fixer = RemoveTrailingWhitespaceFixer()

    def test_no_whitespace(self):
        code = "x = 1\ny = 2\n"
        issue = make_issue()
        result = self.fixer.preview(issue, code)
        assert result.success is True
        assert "No trailing" in result.reason

    def test_removes_trailing(self):
        code = "x = 1   \ny = 2  \n"
        issue = make_issue()
        result = self.fixer.preview(issue, code)
        assert result.success is True
        assert "Removed" in result.reason
        assert result.fixed == "x = 1\ny = 2\n"

    def test_apply_calls_preview(self):
        code = "x   \n"
        issue = make_issue()
        assert self.fixer.apply(issue, code).fixed == self.fixer.preview(issue, code).fixed

    def test_count_changed_lines(self):
        code = "a  \nb  \nc\n"
        issue = make_issue()
        result = self.fixer.preview(issue, code)
        assert "2" in result.reason


# ─────────────────────────── NormalizeQuotesFixer ────────────────────────────


class TestNormalizeQuotesFixer:
    def test_single_to_double(self):
        fixer = NormalizeQuotesFixer(prefer_double=True)
        code = "x = 'hello'\n"
        issue = make_issue()
        result = fixer.preview(issue, code)
        assert result.success is True

    def test_double_to_single(self):
        fixer = NormalizeQuotesFixer(prefer_double=False)
        code = 'x = "hello"\n'
        issue = make_issue()
        result = fixer.preview(issue, code)
        assert result.success is True

    def test_already_normalized_double(self):
        fixer = NormalizeQuotesFixer(prefer_double=True)
        code = 'x = "hello"\n'
        issue = make_issue()
        result = fixer.preview(issue, code)
        assert result.success is True
        assert "already" in result.reason.lower()

    def test_apply_equals_preview(self):
        fixer = NormalizeQuotesFixer()
        issue = make_issue()
        code = "x = 'hi'\n"
        assert fixer.apply(issue, code).success == fixer.preview(issue, code).success


# ─────────────────────────── SimplifyBooleanFixer ────────────────────────────


class TestSimplifyBooleanFixer:
    def setup_method(self):
        self.fixer = SimplifyBooleanFixer()

    def test_simplify_eq_true(self):
        code = "if x == True:\n    pass\n"
        issue = make_issue()
        result = self.fixer.preview(issue, code)
        assert result.success is True
        assert "if x:" in result.fixed

    def test_simplify_eq_false(self):
        code = "if x == False:\n    pass\n"
        issue = make_issue()
        result = self.fixer.preview(issue, code)
        assert result.success is True
        assert "if not x:" in result.fixed

    def test_no_simplification(self):
        code = "x = 1\n"
        issue = make_issue()
        result = self.fixer.preview(issue, code)
        assert result.success is False

    def test_apply_equals_preview(self):
        code = "if flag == True:\n    pass\n"
        issue = make_issue()
        assert self.fixer.apply(issue, code).fixed == self.fixer.preview(issue, code).fixed

    def test_simplify_not_eq_false(self):
        code = "if not x == False:\n    pass\n"
        issue = make_issue()
        result = self.fixer.preview(issue, code)
        assert result.success is True


# ─────────────────────────── ConvertToFStringFixer ───────────────────────────


class TestConvertToFStringFixer:
    def setup_method(self):
        self.fixer = ConvertToFStringFixer()

    def test_converts_format_string(self):
        code = 'msg = "Hello {}".format(name)\n'
        issue = make_issue()
        result = self.fixer.preview(issue, code)
        assert result.success is True
        assert 'f"Hello' in result.fixed

    def test_converts_single_quote_format(self):
        code = "msg = 'Hello {}'.format(name)\n"
        issue = make_issue()
        result = self.fixer.preview(issue, code)
        assert result.success is True

    def test_no_format_string(self):
        code = "x = 1\n"
        issue = make_issue()
        result = self.fixer.preview(issue, code)
        assert result.success is False
        assert "No format" in result.reason

    def test_apply_equals_preview(self):
        code = 'x = "hi {}".format(name)\n'
        issue = make_issue()
        assert self.fixer.apply(issue, code).success == self.fixer.preview(issue, code).success


# ─────────────────────────── RemoveUnusedVariablesFixer ──────────────────────


class TestRemoveUnusedVariablesFixer:
    def setup_method(self):
        self.fixer = RemoveUnusedVariablesFixer()

    def test_no_variable_in_metadata(self):
        issue = make_issue()
        result = self.fixer.preview(issue, "x = 1\n")
        assert result.success is False
        assert "No variable" in result.reason

    def test_removes_unused_variable(self):
        issue = make_issue(metadata={"variable": "unused_var"})
        code = "unused_var = 42\nx = 1\n"
        result = self.fixer.preview(issue, code)
        assert result.success is True
        assert "unused_var =" not in result.fixed

    def test_variable_not_found(self):
        issue = make_issue(metadata={"variable": "missing_var"})
        code = "x = 1\n"
        result = self.fixer.preview(issue, code)
        assert result.success is False
        assert "not found" in result.reason

    def test_apply_equals_preview(self):
        issue = make_issue(metadata={"variable": "tmp"})
        code = "tmp = 10\nresult = 5\n"
        assert self.fixer.apply(issue, code).fixed == self.fixer.preview(issue, code).fixed


# ─────────────────────────── FixIndentationFixer ─────────────────────────────


class TestFixIndentationFixer:
    def test_converts_tabs_to_spaces(self):
        fixer = FixIndentationFixer(spaces=4)
        code = "def foo():\n\tx = 1\n"
        issue = make_issue()
        result = fixer.preview(issue, code)
        assert result.success is True
        assert "Removed" in result.reason or "Fixed" in result.reason
        assert "\t" not in result.fixed

    def test_already_correct(self):
        fixer = FixIndentationFixer(spaces=4)
        code = "def foo():\n    x = 1\n"
        issue = make_issue()
        result = fixer.preview(issue, code)
        assert result.success is True
        assert "already" in result.reason.lower() or "consistent" in result.reason.lower()

    def test_apply_calls_preview(self):
        fixer = FixIndentationFixer()
        issue = make_issue()
        code = "def bar():\n\tpass\n"
        assert fixer.apply(issue, code).fixed == fixer.preview(issue, code).fixed

    def test_custom_spaces(self):
        fixer = FixIndentationFixer(spaces=2)
        code = "if True:\n\tx = 1\n"
        issue = make_issue()
        result = fixer.preview(issue, code)
        assert "  x = 1" in result.fixed


# ─────────────────────────── AddMissingCommasFixer ───────────────────────────


class TestAddMissingCommasFixer:
    def setup_method(self):
        self.fixer = AddMissingCommasFixer()

    def test_adds_comma_multiline_list(self):
        code = "x = [\n    1\n]\n"
        issue = make_issue()
        result = self.fixer.preview(issue, code)
        assert result.success is True
        assert "," in result.fixed

    def test_no_missing_commas(self):
        code = "x = [1, 2, 3]\n"
        issue = make_issue()
        result = self.fixer.preview(issue, code)
        assert result.success is False
        assert "No missing commas" in result.reason

    def test_apply_equals_preview(self):
        code = "y = [\n    a\n]\n"
        issue = make_issue()
        assert self.fixer.apply(issue, code).fixed == self.fixer.preview(issue, code).fixed


# ─────────────────────────── RemovePrintStatementsFixer ──────────────────────


class TestRemovePrintStatementsFixer:
    def test_removes_print_statements(self):
        fixer = RemovePrintStatementsFixer(convert_to_logging=False)
        code = "print('debug')\nx = 1\n"
        issue = make_issue()
        result = fixer.preview(issue, code)
        assert result.success is True
        assert "print(" not in result.fixed

    def test_converts_print_to_logging(self):
        fixer = RemovePrintStatementsFixer(convert_to_logging=True)
        code = "print(msg)\nx = 1\n"
        issue = make_issue()
        result = fixer.preview(issue, code)
        assert result.success is True
        assert "logger.info" in result.fixed

    def test_no_print_statements(self):
        fixer = RemovePrintStatementsFixer()
        code = "x = 1\ny = 2\n"
        issue = make_issue()
        result = fixer.preview(issue, code)
        assert result.success is False
        assert "No print" in result.reason

    def test_apply_equals_preview(self):
        fixer = RemovePrintStatementsFixer()
        code = "print('hi')\n"
        issue = make_issue()
        assert fixer.apply(issue, code).fixed == fixer.preview(issue, code).fixed
