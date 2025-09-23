#!/usr/bin/env python3
"""Block edits to dev-diary.txt file."""

import json
import sys


def main() -> None:
    """Check if attempting to edit dev-diary.txt and block if so."""
    # Read hook data from stdin
    try:
        hook_data = json.load(sys.stdin)
        tool_input = hook_data.get("tool_input", {})
        file_path = tool_input.get("file_path", "")
    except (json.JSONDecodeError, KeyError):
        sys.exit(0)

    # Check if this is dev-diary.txt
    if "dev-diary.txt" in file_path:
        sys.stderr.write("BLOCKED: dev-diary.txt is a user-only file and should not be edited by Claude\n")
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
