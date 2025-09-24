#!/usr/bin/env python3
"""Check if Python files exceed the recommended line count (excluding docstrings and comments)."""

import ast
import json
import sys
from pathlib import Path


def _get_docstring_lines(tree: ast.AST) -> set[int]:
    """Extract line numbers of all docstrings in the AST."""
    docstring_lines: set[int] = set()
    for node in ast.walk(tree):
        # Check for docstrings (string literals as first statement)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Module)):
            docstring = ast.get_docstring(node, clean=False)
            if (
                docstring
                and node.body
                and isinstance(node.body[0], ast.Expr)
                and isinstance(node.body[0].value, ast.Constant)
                and node.body[0].end_lineno is not None
            ):
                first_stmt = node.body[0]
                # Add all lines that the docstring spans
                end_line = first_stmt.end_lineno
                if end_line is not None:
                    for line_no in range(first_stmt.lineno, end_line + 1):
                        docstring_lines.add(line_no)
    return docstring_lines


def _count_logic_lines_from_source(source: str, docstring_lines: set[int]) -> int:
    """Count logic lines from source code, excluding docstrings and comments."""
    lines = source.splitlines()
    logic_lines = 0
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # Skip empty lines, pure comments, and docstring lines
        if stripped and not stripped.startswith("#") and i not in docstring_lines:
            logic_lines += 1
    return logic_lines


def _fallback_line_count(filepath: str) -> int:
    """Fallback line count when AST parsing fails."""
    try:
        with Path(filepath).open(encoding="utf-8") as f:
            return len([line for line in f if line.strip() and not line.strip().startswith("#")])
    except OSError:
        return 0


def count_logic_lines(filepath: str) -> int:
    """Count non-docstring, non-comment lines in a Python file."""
    try:
        with Path(filepath).open(encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)
        docstring_lines = _get_docstring_lines(tree)
        return _count_logic_lines_from_source(source, docstring_lines)

    except (SyntaxError, ValueError, OSError):
        # If we can't parse, fall back to simple line count
        return _fallback_line_count(filepath)


def main() -> None:
    """Check file size and print warnings."""
    # Read hook data from stdin
    try:
        hook_data = json.load(sys.stdin)
        tool_input = hook_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
    except (json.JSONDecodeError, KeyError):
        sys.exit(0)

    # Skip demo files (they're excluded from linting)
    if "demo_files/" in file_path:
        sys.exit(0)

    # Skip test files
    if Path(file_path).name.startswith("test_"):
        sys.exit(0)

    # Check the file size
    if Path(file_path).exists():
        logic_lines = count_logic_lines(file_path)

        if logic_lines > 400:
            message = (
                f"⚠️ File {Path(file_path).name} has {logic_lines} logic lines "
                "(excluding docstrings/comments). Consider splitting into smaller, "
                "focused modules (recommended: 300-400 lines max). "
                "Non-test Python files should be kept focused - split them into "
                "smaller modules if they exceed ~400 lines of non-documentation code."
            )
            sys.stderr.write(message + "\n")
            sys.exit(1)
        elif logic_lines > 300:
            message = (
                f"INFO: File {Path(file_path).name} has {logic_lines} logic lines. "
                "Approaching recommended limit of 300-400 lines. Consider refactoring "
                "if the file continues to grow."
            )
            sys.stderr.write(message + "\n")
            sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
