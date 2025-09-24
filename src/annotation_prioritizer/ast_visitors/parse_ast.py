"""Common AST parsing utilities for file analysis.

This module provides centralized file parsing functionality to ensure consistent
AST generation and single-read semantics across the annotation prioritizer.
By parsing files once and passing the AST and source code to downstream functions,
we eliminate duplicate I/O operations and parsing overhead.

The parse_ast_from_file function handles common error cases (missing files,
syntax errors) gracefully, returning None to allow callers to handle failures
appropriately.
"""

import ast
from pathlib import Path


def parse_ast_from_source(source: str, filename: str) -> tuple[ast.Module, str] | None:
    """Parse Python source code into an AST.

    Args:
        source: Python source code as a string
        filename: Filename to use in error messages and tracebacks.

    Returns:
        Tuple of (AST module, source code) on success, None on syntax error
    """
    try:
        tree = ast.parse(source, filename=filename)
    except SyntaxError:
        return None
    else:
        return (tree, source)


def parse_ast_from_file(file_path: Path) -> tuple[ast.Module, str] | None:
    """Parse a Python file into an AST and return source code.

    Args:
        file_path: Path to the Python source file

    Returns:
        Tuple of (AST module, source code) on success, None on failure
        (file not found, syntax error, or encoding error)
    """
    if not file_path.exists():
        return None

    try:
        source_code = file_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None

    return parse_ast_from_source(source_code, str(file_path))
