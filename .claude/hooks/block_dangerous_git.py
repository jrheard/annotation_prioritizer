#!/usr/bin/env python3
"""Block dangerous git commands that could cause data loss."""

from __future__ import annotations

import json
import re
import sys


def is_dangerous_command(command: str) -> tuple[bool, str | None]:
    """Check if a git command is dangerous and should be blocked.

    Args:
        command: The bash command string to check

    Returns:
        A tuple of (is_dangerous, reason)
        - is_dangerous: True if command should be blocked
        - reason: Description of why it's blocked, or None if safe
    """
    # Pattern for git reset --hard at start of command or after command separator
    # Matches: ^git reset --hard, or after &&, ||, ; with optional whitespace
    if re.search(r"(^|&&|\|\||;)\s*git\s+reset\s+--hard\b", command):
        return True, "git reset --hard discards uncommitted changes and is destructive"

    # Pattern for git push at start of command or after command separator
    if re.search(r"(^|&&|\|\||;)\s*git\s+push\b", command):
        return True, "git push modifies remote repository state"

    return False, None


def format_error_message(reason: str) -> str:
    """Format an error message for blocked commands.

    Args:
        reason: The reason the command is blocked

    Returns:
        A formatted error message with helpful context
    """
    return (
        f"BLOCKED: Dangerous git command detected. {reason}\n\n"
        "This hook prevents:\n"
        "  - git reset --hard (data loss)\n"
        "  - git push (remote modifications)\n\n"
        "If you need to run these commands, ask the user to run them manually.\n"
    )


def main() -> None:
    """Check bash commands for dangerous git operations.

    This hook is called by Claude Code before executing bash commands.
    It receives JSON data via stdin containing tool information.
    """
    # Read hook data from stdin
    try:
        hook_data = json.load(sys.stdin)
        tool_input = hook_data.get("tool_input", {})
        command = tool_input.get("command", "")
    except (json.JSONDecodeError, KeyError):
        # Invalid JSON or missing fields - don't block
        sys.exit(0)

    # Check if command is dangerous
    is_dangerous, reason = is_dangerous_command(command)

    if is_dangerous:
        # Format and display error message
        assert reason is not None  # Type guard: reason is always set when is_dangerous is True
        sys.stderr.write(format_error_message(reason))
        sys.exit(2)  # Exit code 2 blocks the command

    # Command is safe
    sys.exit(0)


if __name__ == "__main__":
    main()
