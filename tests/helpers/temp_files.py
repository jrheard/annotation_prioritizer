"""Temporary file utilities for testing."""

import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def temp_python_file(content: str) -> Iterator[Path]:
    """Create a temporary Python file with the given content.

    Args:
        content: Python source code to write to the file

    Yields:
        Path: Path to the temporary file

    Example:
        with temp_python_file('def test(): pass') as path:
            result = parse_function_definitions(path)
            assert len(result) == 1

    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(content)
        f.flush()
        temp_path = f.name

    temp_path = Path(temp_path)
    try:
        yield temp_path
    finally:
        temp_path.unlink()
