"""File-to-AST parsing."""

import ast
from pathlib import Path


def parse_ast_from_file(file_path: Path) -> tuple[ast.Module, str] | None:
    """Parse a Python file into an AST and return source code.

    Args:
        file_path: Path to the Python source file

    Returns:
        Tuple of (AST module, source code) on success, None on failure
        (file not found or syntax error)
    """
    if not file_path.exists():
        return None

    try:
        source_code = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source_code, filename=str(file_path))
    except (OSError, SyntaxError):
        return None
    else:
        return (tree, source_code)
