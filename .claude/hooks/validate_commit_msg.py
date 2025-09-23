#!/usr/bin/env python3
"""Validate git commit messages follow conventional commit format."""

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


def validate_commit_message(message: str) -> tuple[bool, str | None]:
    """Validate commit message format."""
    # Pattern for conventional commits: type(scope)?: description
    # We'll be flexible on scope (optional) but strict on type
    pattern = r"^(" + "|".join(VALID_TYPES.keys()) + r")(\([^)]+\))?:\s+.+"

    if not re.match(pattern, message, re.IGNORECASE):
        return False, f"Message must start with one of: {', '.join(VALID_TYPES.keys())}"

    # Extract the type
    commit_type = message.split(":")[0].split("(")[0].lower()
    if commit_type not in VALID_TYPES:
        return False, f"Invalid commit type: {commit_type}"

    return True, None


def main() -> None:
    """Validate commit messages in git commands."""
    # Read hook data from stdin
    try:
        hook_data = json.load(sys.stdin)
        tool_name = hook_data.get("tool_name", "")
        tool_input = hook_data.get("tool_input", {})
        command = tool_input.get("command", "")
    except (json.JSONDecodeError, KeyError):
        sys.exit(0)

    # Only check Bash commands
    if tool_name != "Bash":
        sys.exit(0)

    # Look for git commit commands
    if "git commit" not in command:
        sys.exit(0)

    # Try to extract the commit message
    # Handle various formats: -m "message", -m"message", -m 'message', etc.
    message_match = re.search(r'-m\s*["\']([^"\']+)["\']', command)
    if not message_match:
        # Also check for heredoc format used by Claude
        heredoc_match = re.search(r'-m\s*"\$\(cat\s*<<.*?\n(.*?)\n.*?EOF', command, re.DOTALL)
        if heredoc_match:
            message = heredoc_match.group(1).strip()
            # Remove the Claude signature lines if present
            lines = message.split("\n")
            if lines:
                message = lines[0]  # Just validate the first line
        else:
            sys.exit(0)  # Can't find message, don't block
    else:
        message = message_match.group(1)

    # Validate the message
    valid, error = validate_commit_message(message)

    if not valid:
        types_desc = "\n".join([f"  - {t}: {desc}" for t, desc in VALID_TYPES.items()])
        msg = (
            f"BLOCKED: Invalid commit message format. {error}\n\n"
            f"Valid types:\n{types_desc}\n\n"
            "Format: <type>: <description>\n"
            "Example: feat: add dark mode toggle\n"
        )
        sys.stderr.write(msg)
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
