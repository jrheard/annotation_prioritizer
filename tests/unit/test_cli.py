"""Unit tests for CLI module (no I/O operations)."""

from pathlib import Path
from unittest.mock import patch

from annotation_prioritizer.cli import parse_args


def test_parse_args_basic() -> None:
    """Test basic argument parsing."""
    with patch("sys.argv", ["annotation-prioritizer", "test.py"]):
        args = parse_args()
        assert args.target == Path("test.py")
        assert args.min_calls == 0


def test_parse_args_with_min_calls() -> None:
    """Test argument parsing with min-calls option."""
    with patch("sys.argv", ["annotation-prioritizer", "test.py", "--min-calls", "5"]):
        args = parse_args()
        assert args.target == Path("test.py")
        assert args.min_calls == 5


def test_parse_args_with_debug() -> None:
    """Test argument parsing with debug option."""
    with patch("sys.argv", ["annotation-prioritizer", "test.py", "--debug"]):
        args = parse_args()
        assert args.target == Path("test.py")
        assert args.debug is True
        assert args.min_calls == 0


def test_parse_args_without_debug() -> None:
    """Test argument parsing without debug option defaults to false."""
    with patch("sys.argv", ["annotation-prioritizer", "test.py"]):
        args = parse_args()
        assert args.target == Path("test.py")
        assert args.debug is False
