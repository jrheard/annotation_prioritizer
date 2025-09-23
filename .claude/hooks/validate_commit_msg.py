#!/usr/bin/env python3
"""Validate git commit messages follow conventional commit format."""

from __future__ import annotations

import json
import re
import sys

VALID_TYPES = {
    "feat": "New user-facing functionality only (core app features)",
    "fix": "Bug fixes",
    "docs": "Documentation changes (docstrings, comments, README, planning docs, etc.)",
    "refactor": "Code restructuring without behavior changes",
    "test": "Test changes",
    "chore": "Tooling, dependencies, build config, CI/CD",
}


def extract_commit_message(command: str) -> str | None:
    r"""Extract commit message from a git commit command.

    Handles multiple formats:
    1. Heredoc format: git commit -m "$(cat <<'EOF'\n...\nEOF\n)"
       - Used by tools that need multi-line messages with special characters
       - Must be checked first as it contains quotes that would confuse simple patterns

    2. Simple quoted format: git commit -m "message" or git commit -m 'message'
       - Standard single-line commit messages
       - Most common format for human-written commits

    Args:
        command: The full bash command string containing git commit

    Returns:
        The extracted commit message (first line only for multi-line messages),
        or None if no message could be extracted
    """
    # First check for heredoc format (must check before simple quotes)
    # This pattern matches: -m "$(cat <<DELIMITER...DELIMITER)"
    # where DELIMITER is commonly 'EOF' but can be any string
    heredoc_pattern = r'-m\s*"\$\(cat\s*<<[\'"]?(\w+)[\'"]?\n(.*?)\n\1'
    heredoc_match = re.search(heredoc_pattern, command, re.DOTALL)

    if heredoc_match:
        # Extract the full message content (group 2)
        full_message = heredoc_match.group(2).strip()
        # For validation, only use the first line (conventional commit format)
        lines = full_message.split("\n")
        return lines[0] if lines else None

    # Handle simple quoted formats: -m "message" or -m 'message'
    # This pattern captures the message between matching quotes
    simple_pattern = r'-m\s*(["\'])([^\1]*?)\1'
    simple_match = re.search(simple_pattern, command)

    if simple_match:
        return simple_match.group(2)

    return None


def validate_commit_message(message: str) -> tuple[bool, str | None]:
    """Validate that a commit message follows conventional commit format.

    Conventional commit format: <type>(<scope>)?: <description>
    - type: One of the predefined types (feat, fix, docs, etc.)
    - scope: Optional, describes the section of code affected
    - description: Brief description of the change

    Args:
        message: The commit message to validate (first line only)

    Returns:
        A tuple of (is_valid, error_message)
        - is_valid: True if message follows format
        - error_message: Description of validation failure, or None if valid
    """
    # Build regex pattern from valid types
    # Pattern: ^(type1|type2|...)(\([^)]+\))?:\s+.+
    types_pattern = "|".join(VALID_TYPES.keys())
    full_pattern = rf"^({types_pattern})(\([^)]+\))?:\s+.+"

    # Check if message matches the pattern (case-insensitive)
    if not re.match(full_pattern, message, re.IGNORECASE):
        return False, f"Message must start with one of: {', '.join(VALID_TYPES.keys())}"

    # Extract and validate the commit type
    # Split on ':' to get type part, then split on '(' to remove scope if present
    type_part = message.split(":")[0]
    commit_type = type_part.split("(")[0].lower()

    if commit_type not in VALID_TYPES:
        return False, f"Invalid commit type: {commit_type}"

    return True, None


def format_validation_error(error: str) -> str:
    """Format a validation error message for display.

    Args:
        error: The basic error message

    Returns:
        A formatted error message with helpful context
    """
    types_desc = "\n".join([f"  - {t}: {desc}" for t, desc in VALID_TYPES.items()])
    return (
        f"BLOCKED: Invalid commit message format. {error}\n\n"
        f"Valid types:\n{types_desc}\n\n"
        "Format: <type>: <description>\n"
        "Example: feat: add dark mode toggle\n"
    )


def main() -> None:
    """Validate commit messages in git commands.

    This hook is called by Claude Code before executing bash commands.
    It receives JSON data via stdin containing tool information.
    """
    # Read hook data from stdin
    try:
        hook_data = json.load(sys.stdin)
        tool_name = hook_data.get("tool_name", "")
        tool_input = hook_data.get("tool_input", {})
        command = tool_input.get("command", "")
    except (json.JSONDecodeError, KeyError):
        # Invalid JSON or missing fields - don't block
        sys.exit(0)

    # Only validate Bash commands
    if tool_name != "Bash":
        sys.exit(0)

    # Only validate git commit commands
    if "git commit" not in command:
        sys.exit(0)

    # Try to extract the commit message
    message = extract_commit_message(command)
    if message is None:
        # Could not extract message - don't block
        # This might be a commit with -F flag or other format we don't handle
        sys.exit(0)

    # Validate the commit message format
    is_valid, error = validate_commit_message(message)

    if not is_valid:
        # Format and display error message
        assert error is not None  # Type guard: error is always set when is_valid is False
        sys.stderr.write(format_validation_error(error))
        sys.exit(2)  # Exit code 2 indicates validation failure

    # Message is valid
    sys.exit(0)


if __name__ == "__main__":
    main()
