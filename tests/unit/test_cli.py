"""Tests for CLI module."""

import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from annotation_prioritizer.cli import main, parse_args
from annotation_prioritizer.models import AnalysisResult, UnresolvableCall
from tests.helpers.console import assert_console_contains, capture_console_output
from tests.helpers.factories import make_priority


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


def test_main_file_not_exists() -> None:
    """Test main() with non-existent file."""
    with (
        capture_console_output() as (test_console, output),
        patch("annotation_prioritizer.cli.Console", return_value=test_console),
        patch("sys.argv", ["annotation-prioritizer", "nonexistent.py"]),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    assert_console_contains(output, "does not exist")


def test_main_not_python_file() -> None:
    """Test main() with non-Python file."""
    with (
        tempfile.NamedTemporaryFile(suffix=".txt") as tmp,
        capture_console_output() as (test_console, output),
        patch("annotation_prioritizer.cli.Console", return_value=test_console),
        patch("sys.argv", ["annotation-prioritizer", tmp.name]),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    assert_console_contains(output, "not a Python file")


def test_main_successful_analysis() -> None:
    """Test successful analysis of a Python file."""
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as tmp:
        tmp.write("def test_func(): pass\n")
        tmp.flush()

        # Create mock data
        mock_priority = make_priority(
            "test_func",
            param_score=1.0,
            return_score=0.0,
            call_count=3,
            line_number=1,
            file_path=Path(tmp.name),
        )

        with (
            patch("annotation_prioritizer.cli.Console") as mock_console,
            patch("annotation_prioritizer.cli.analyze_file") as mock_analyze,
            patch("annotation_prioritizer.cli.display_results") as mock_display,
            patch("sys.argv", ["annotation-prioritizer", tmp.name]),
            capture_console_output() as (test_console, _),
        ):
            mock_console.return_value = test_console
            mock_analyze.return_value = AnalysisResult(priorities=(mock_priority,), unresolvable_calls=())

            main()

            mock_analyze.assert_called_once_with(tmp.name)
            mock_display.assert_called_once_with(test_console, (mock_priority,))


def test_main_with_min_calls_filter() -> None:
    """Test main() with min-calls filter."""
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as tmp:
        tmp.write("def test_func(): pass\n")
        tmp.flush()

        # Create mock data with low call count
        mock_priority = make_priority(
            "test_func",
            param_score=1.0,
            return_score=0.0,
            call_count=1,  # Low call count
            line_number=1,
            file_path=Path(tmp.name),
        )

        with (
            patch("annotation_prioritizer.cli.Console") as mock_console,
            patch("annotation_prioritizer.cli.analyze_file") as mock_analyze,
            patch("annotation_prioritizer.cli.display_results") as mock_display,
            patch("sys.argv", ["annotation-prioritizer", tmp.name, "--min-calls", "5"]),
            capture_console_output() as (test_console, _),
        ):
            mock_console.return_value = test_console
            mock_analyze.return_value = AnalysisResult(priorities=(mock_priority,), unresolvable_calls=())

            main()

            mock_analyze.assert_called_once_with(tmp.name)
            # Should be called with empty tuple due to filtering
            mock_display.assert_called_once_with(test_console, ())


def test_main_with_unresolvable_calls() -> None:
    """Test main() with unresolvable calls displays warning."""
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as tmp:
        tmp.write("def test_func(): pass\n")
        tmp.flush()

        # Create mock data
        mock_priority = make_priority(
            "test_func",
            param_score=1.0,
            return_score=0.0,
            call_count=3,
            line_number=1,
            file_path=Path(tmp.name),
        )

        mock_unresolvable = UnresolvableCall(line_number=5, call_text="processor.process()")

        with (
            patch("annotation_prioritizer.cli.Console") as mock_console,
            patch("annotation_prioritizer.cli.analyze_file") as mock_analyze,
            patch("annotation_prioritizer.cli.display_results") as mock_display,
            patch("annotation_prioritizer.cli.display_unresolvable_summary") as mock_unresolvable_display,
            patch("sys.argv", ["annotation-prioritizer", tmp.name]),
            capture_console_output() as (test_console, _),
        ):
            mock_console.return_value = test_console
            mock_analyze.return_value = AnalysisResult(
                priorities=(mock_priority,), unresolvable_calls=(mock_unresolvable,)
            )

            main()

            mock_analyze.assert_called_once_with(tmp.name)
            mock_unresolvable_display.assert_called_once_with(test_console, (mock_unresolvable,))
            mock_display.assert_called_once_with(test_console, (mock_priority,))


def test_main_analysis_error() -> None:
    """Test main() when analysis raises an exception."""
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as tmp:
        tmp.write("def test_func(): pass\n")
        tmp.flush()

        with (
            capture_console_output() as (test_console, output),
            patch("annotation_prioritizer.cli.Console", return_value=test_console),
            patch("annotation_prioritizer.cli.analyze_file", side_effect=ValueError("Test error")),
            patch("sys.argv", ["annotation-prioritizer", tmp.name]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 1
        assert_console_contains(output, "Error analyzing file", "Test error")


def test_main_directory_input() -> None:
    """Test main() with directory instead of file."""
    with (
        tempfile.TemporaryDirectory() as tmp_dir,
        capture_console_output() as (test_console, output),
        patch("annotation_prioritizer.cli.Console", return_value=test_console),
        patch("sys.argv", ["annotation-prioritizer", tmp_dir]),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    assert_console_contains(output, "is not a file")


def test_main_with_debug_logging() -> None:
    """Test that debug flag configures logging correctly."""
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as tmp:
        tmp.write("def test_func(): pass\n")
        tmp.flush()

        # Create mock data
        mock_priority = make_priority(
            "test_func",
            param_score=1.0,
            return_score=0.0,
            call_count=3,
            line_number=1,
            file_path=Path(tmp.name),
        )

        with (
            patch("annotation_prioritizer.cli.Console") as mock_console,
            patch("annotation_prioritizer.cli.analyze_file") as mock_analyze,
            patch("annotation_prioritizer.cli.display_results"),
            patch("annotation_prioritizer.cli.logging.basicConfig") as mock_logging_config,
            patch("annotation_prioritizer.cli.logger.debug") as mock_debug,
            patch("sys.argv", ["annotation-prioritizer", tmp.name, "--debug"]),
            capture_console_output() as (test_console, _),
        ):
            mock_console.return_value = test_console
            mock_analyze.return_value = AnalysisResult(priorities=(mock_priority,), unresolvable_calls=())

            main()

            # Verify logging was configured with DEBUG level
            mock_logging_config.assert_called_once_with(
                level=logging.DEBUG,
                format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            )
            mock_debug.assert_called_once_with("Debug logging enabled")
