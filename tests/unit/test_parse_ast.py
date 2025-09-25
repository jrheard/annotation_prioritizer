"""Unit tests for the parse_ast module (no I/O operations)."""

import ast

from annotation_prioritizer.ast_visitors.parse_ast import parse_ast_from_source


def test_parse_ast_from_source_valid_code() -> None:
    """Test parsing valid Python source code."""
    source = "def foo():\n    pass\n"
    result = parse_ast_from_source(source, "test.py")
    assert result is not None
    tree, returned_source = result
    assert isinstance(tree, ast.Module)
    assert returned_source == source
    # Verify the AST contains a function definition
    assert len(tree.body) == 1
    assert isinstance(tree.body[0], ast.FunctionDef)
    assert tree.body[0].name == "foo"


def test_parse_ast_from_source_syntax_error() -> None:
    """Test parsing source with syntax errors."""
    # Invalid Python syntax - unclosed parenthesis
    source = "def foo(\n"
    result = parse_ast_from_source(source, "test.py")
    assert result is None


def test_parse_ast_from_source_empty() -> None:
    """Test parsing empty source code."""
    source = ""
    result = parse_ast_from_source(source, "empty.py")
    assert result is not None
    tree, returned_source = result
    assert isinstance(tree, ast.Module)
    assert returned_source == ""
    assert len(tree.body) == 0


def test_parse_ast_from_source_unicode() -> None:
    """Test parsing source with Unicode characters."""
    source = "# Comment with emoji 🎉\ndef greet():\n    return '你好'\n"
    result = parse_ast_from_source(source, "unicode.py")
    assert result is not None
    tree, returned_source = result
    assert isinstance(tree, ast.Module)
    assert returned_source == source
    assert len(tree.body) == 1
    assert isinstance(tree.body[0], ast.FunctionDef)
    assert tree.body[0].name == "greet"


def test_parse_ast_from_source_complex_structure() -> None:
    """Test parsing source with complex Python structures."""
    source = '''"""Module docstring."""
import sys
from typing import Optional

class MyClass:
    """A test class."""

    def __init__(self) -> None:
        self.value = 42

def my_function(x: int) -> Optional[int]:
    """A test function."""
    if x > 0:
        return x * 2
    return None

MY_CONSTANT = 100
'''
    result = parse_ast_from_source(source, "complex.py")
    assert result is not None
    tree, returned_source = result
    assert isinstance(tree, ast.Module)
    assert returned_source == source
    # Check we have the expected elements
    # Docstring, import, from import, class, function, assignment
    assert len(tree.body) == 6


def test_parse_ast_from_source_with_type_annotations() -> None:
    """Test parsing source with various type annotations."""
    source = """
from typing import List, Dict, Optional

def process(items: List[str], config: Dict[str, int]) -> Optional[int]:
    return config.get(items[0]) if items else None
"""
    result = parse_ast_from_source(source, "typed.py")
    assert result is not None
    tree, _ = result
    assert isinstance(tree, ast.Module)
    # Import statement and function definition
    assert len(tree.body) == 2
    func = tree.body[1]
    assert isinstance(func, ast.FunctionDef)
    assert func.name == "process"
    # Check that annotations are present
    assert func.args.args[0].annotation is not None
    assert func.args.args[1].annotation is not None
    assert func.returns is not None


def test_parse_ast_from_source_async_code() -> None:
    """Test parsing async/await Python code."""
    source = """
async def fetch_data():
    await some_operation()
    return "data"
"""
    result = parse_ast_from_source(source, "async.py")
    assert result is not None
    tree, _ = result
    assert isinstance(tree, ast.Module)
    assert len(tree.body) == 1
    func = tree.body[0]
    assert isinstance(func, ast.AsyncFunctionDef)
    assert func.name == "fetch_data"


def test_parse_ast_from_source_multiline_strings() -> None:
    """Test parsing source with multiline strings."""
    source = '''
def get_query():
    return """
    SELECT *
    FROM users
    WHERE active = true
    """
'''
    result = parse_ast_from_source(source, "multiline.py")
    assert result is not None
    tree, _ = result
    assert isinstance(tree, ast.Module)
    assert len(tree.body) == 1
    func = tree.body[0]
    assert isinstance(func, ast.FunctionDef)
    assert func.name == "get_query"
