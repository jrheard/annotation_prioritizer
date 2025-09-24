"""Tests for the parse_ast module."""

import ast
import tempfile
from pathlib import Path

from annotation_prioritizer.ast_visitors.parse_ast import parse_ast_from_file


def test_successful_parsing() -> None:
    """Test parsing a valid Python file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        source = "def foo():\n    pass\n"
        f.write(source)
        f.flush()
        file_path = Path(f.name)

    try:
        result = parse_ast_from_file(file_path)
        assert result is not None
        tree, source_code = result
        assert isinstance(tree, ast.Module)
        assert source_code == "def foo():\n    pass\n"
        # Verify the AST contains a function definition
        assert len(tree.body) == 1
        assert isinstance(tree.body[0], ast.FunctionDef)
        assert tree.body[0].name == "foo"
    finally:
        file_path.unlink()


def test_file_not_found() -> None:
    """Test parsing a non-existent file."""
    file_path = Path("/nonexistent/path/to/file.py")
    result = parse_ast_from_file(file_path)
    assert result is None


def test_syntax_error_in_file() -> None:
    """Test parsing a file with syntax errors."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        # Invalid Python syntax
        f.write("def foo(\n")
        f.flush()
        file_path = Path(f.name)

    try:
        result = parse_ast_from_file(file_path)
        assert result is None
    finally:
        file_path.unlink()


def test_empty_file() -> None:
    """Test parsing an empty file."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        # Empty file
        f.write("")
        f.flush()
        file_path = Path(f.name)

    try:
        result = parse_ast_from_file(file_path)
        assert result is not None
        tree, source_code = result
        assert isinstance(tree, ast.Module)
        assert source_code == ""
        assert len(tree.body) == 0
    finally:
        file_path.unlink()


def test_file_with_unicode() -> None:
    """Test parsing a file with Unicode characters."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        source = "# Comment with emoji 🎉\ndef greet():\n    return '你好'\n"
        f.write(source)
        f.flush()
        file_path = Path(f.name)

    try:
        result = parse_ast_from_file(file_path)
        assert result is not None
        tree, source_code = result
        assert isinstance(tree, ast.Module)
        assert source_code == source
        assert len(tree.body) == 1
        assert isinstance(tree.body[0], ast.FunctionDef)
    finally:
        file_path.unlink()


def test_complex_file_structure() -> None:
    """Test parsing a file with complex Python structures."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
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
        f.write(source)
        f.flush()
        file_path = Path(f.name)

    try:
        result = parse_ast_from_file(file_path)
        assert result is not None
        tree, source_code = result
        assert isinstance(tree, ast.Module)
        assert source_code == source
        # Check we have the expected elements
        # Docstring, import, from import, class, function, assignment
        assert len(tree.body) == 6
    finally:
        file_path.unlink()


def test_file_read_permission_error() -> None:
    """Test handling of file read permission errors."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write("def foo(): pass\n")
        f.flush()
        file_path = Path(f.name)

    try:
        # Remove read permissions
        file_path.chmod(0o000)
        result = parse_ast_from_file(file_path)
        # Should return None due to OSError
        assert result is None
    finally:
        # Restore permissions before cleanup
        file_path.chmod(0o644)
        file_path.unlink()
