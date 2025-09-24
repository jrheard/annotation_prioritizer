#!/usr/bin/env python3
"""Check for generic module names that should be avoided."""

import json
import re
import sys
from pathlib import Path

GENERIC_PATTERNS = [
    r".*_utils\.py$",
    r".*_helpers\.py$",
    r".*_misc\.py$",
    r".*_common\.py$",
    r".*_general\.py$",
]


def is_generic_name(filename: str) -> bool:
    """Check if filename matches generic patterns."""
    return any(re.match(pattern, filename) for pattern in GENERIC_PATTERNS)


def main() -> None:
    """Check for generic module names in new file operations."""
    # Read hook data from stdin
    try:
        hook_data = json.load(sys.stdin)
        tool_input = hook_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
    except (json.JSONDecodeError, KeyError):
        sys.exit(0)

    # Skip demo files and test files
    if "demo_files/" in file_path or "/tests/" in file_path:
        sys.exit(0)

    filename = Path(file_path).name

    if is_generic_name(filename):
        msg = (
            f"⚠️ Generic module name '{filename}' detected. "
            "Consider using a more specific name that describes the functionality "
            "(e.g., 'ast_arguments.py' instead of 'ast_utils.py'). "
            "This helps avoid files becoming dumping grounds for miscellaneous functions.\n"
        )
        sys.stderr.write(msg)
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()
