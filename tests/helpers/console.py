"""Console testing utilities."""

from collections.abc import Iterator
from contextlib import contextmanager
from io import StringIO

from rich.console import Console


@contextmanager
def capture_console_output(
    width: int = 80, *, force_terminal: bool = False
) -> Iterator[tuple[Console, StringIO]]:
    """Create a Console instance with captured output.

    Args:
        width: Console width in characters
        force_terminal: Whether to force terminal mode

    Yields:
        tuple[Console, StringIO]: Console instance and output buffer

    Example:
        with capture_console_output() as (console, output):
            display_results(console, data)
            output_str = output.getvalue()
            assert "Expected text" in output_str

    """
    output = StringIO()
    console = Console(file=output, force_terminal=force_terminal, width=width)
    yield console, output


def assert_console_contains(output: StringIO, *expected_texts: str) -> None:
    """Assert that console output contains all expected text fragments.

    Args:
        output: StringIO buffer from capture_console_output
        expected_texts: Text fragments that should be present

    Example:
        with capture_console_output() as (console, output):
            print_summary_stats(console, data)
            assert_console_contains(output, "Total functions", "High priority")

    """
    output_str = output.getvalue()
    for text in expected_texts:
        assert text in output_str, f"Expected '{text}' not found in output: {output_str!r}"
