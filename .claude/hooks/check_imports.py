#!/usr/bin/env python3
"""Check for relative imports in Python files and block if found."""

import ast
import json
import sys
from pathlib import Path


def has_relative_imports(source_code: str) -> list[dict[str, str | int]]:
    """Check if source code contains relative imports."""
    try:
        tree = ast.parse(source_code)
        relative_imports: list[dict[str, str | int]] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level > 0:
                # level > 0 means relative import (e.g., from . import x, from .. import y)
                import_str = "." * node.level
                if node.module:
                    import_str += node.module
                relative_imports.append({"line": node.lineno, "import": f"from {import_str} import ..."})

    except SyntaxError:
        # If we can't parse, don't block
        return []
    else:
        return relative_imports


def check_file_content(content: str, filepath: str) -> str | None:
    """Check if the file content (old_string or new_string) contains relative imports."""
    relative_imports = has_relative_imports(content)
    if relative_imports:
        imports_desc = ", ".join([f"line {imp['line']}: {imp['import']}" for imp in relative_imports])
        return f"Found relative imports in {filepath}: {imports_desc}"
    return None


def main() -> None:
    """Check for relative imports in file operations."""
    # Read hook data from stdin
    try:
        hook_data = json.load(sys.stdin)
        tool_input = hook_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
    except (json.JSONDecodeError, KeyError):
        sys.exit(0)
    if not file_path.endswith(".py"):
        sys.exit(0)

    # Skip demo files
    if "demo_files/" in file_path:
        sys.exit(0)

    # For Edit operations, check new_string
    if "new_string" in tool_input:
        error = check_file_content(tool_input["new_string"], Path(file_path).name)
        if error:
            msg = (
                f"BLOCKED: Relative imports not allowed. {error}. "
                "Use absolute imports instead (per project guidelines).\n"
            )
            sys.stderr.write(msg)
            sys.exit(2)

    # For Write operations, check content
    elif "content" in tool_input:
        error = check_file_content(tool_input["content"], Path(file_path).name)
        if error:
            msg = (
                f"BLOCKED: Relative imports not allowed. {error}. "
                "Use absolute imports instead (per project guidelines).\n"
            )
            sys.stderr.write(msg)
            sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
