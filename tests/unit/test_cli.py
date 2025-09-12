"""Tests for CLI module."""

from io import StringIO
from unittest.mock import patch

from rich.console import Console

from annotation_prioritizer.cli import main


def test_main_prints_hello_world() -> None:
    """Test that main() prints hello world message."""
    output = StringIO()

    # Mock Console class to return our test console instance
    with patch("annotation_prioritizer.cli.Console") as mock_console:
        test_console = Console(file=output, force_terminal=False, width=80)
        mock_console.return_value = test_console

        main()
        output_str = output.getvalue()
        if "Hello, World!" not in output_str:
            msg = f"Expected 'Hello, World!' in output, got: {output_str!r}"
            raise AssertionError(msg)
