"""Tests for CLI module."""

from io import StringIO

import pytest
from rich.console import Console

from annotation_prioritizer.cli import main


def test_main_prints_hello_world() -> None:
    """Test that main() prints hello world message."""
    output = StringIO()
    console = Console(file=output, force_terminal=False, width=80)
    
    # Monkey patch the console in the cli module
    import annotation_prioritizer.cli as cli_module
    original_console = None
    if hasattr(cli_module, 'console'):
        original_console = cli_module.console
    
    try:
        # Replace the console in the module
        cli_module.console = console
        main()
        output_str = output.getvalue()
        assert "Hello, World!" in output_str
    finally:
        # Restore original console if it existed
        if original_console is not None:
            cli_module.console = original_console