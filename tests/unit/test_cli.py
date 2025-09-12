"""Tests for CLI module."""

import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from rich.console import Console

from annotation_prioritizer.cli import main, parse_args
from annotation_prioritizer.models import AnnotationScore, FunctionInfo, FunctionPriority


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


def test_main_file_not_exists() -> None:
    """Test main() with non-existent file."""
    output = StringIO()
    test_console = Console(file=output, force_terminal=False, width=80)

    with (
        patch("annotation_prioritizer.cli.Console", return_value=test_console),
        patch("sys.argv", ["annotation-prioritizer", "nonexistent.py"]),
        pytest.raises(SystemExit) as exc_info,
    ):
        main()

    assert exc_info.value.code == 1
    output_str = output.getvalue()
    assert "does not exist" in output_str


def test_main_not_python_file() -> None:
    """Test main() with non-Python file."""
    with tempfile.NamedTemporaryFile(suffix=".txt") as tmp:
        output = StringIO()
        test_console = Console(file=output, force_terminal=False, width=80)

        with (
            patch("annotation_prioritizer.cli.Console", return_value=test_console),
            patch("sys.argv", ["annotation-prioritizer", tmp.name]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 1
        output_str = output.getvalue()
        assert "not a Python file" in output_str


def test_main_successful_analysis() -> None:
    """Test successful analysis of a Python file."""
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as tmp:
        tmp.write("def test_func(): pass\n")
        tmp.flush()

        # Create mock data
        mock_priority = FunctionPriority(
            function_info=FunctionInfo(
                name="test_func",
                qualified_name="test_func",
                parameters=(),
                has_return_annotation=False,
                line_number=1,
                file_path=tmp.name,
            ),
            annotation_score=AnnotationScore(
                function_qualified_name="test_func",
                parameter_score=1.0,
                return_score=0.0,
                total_score=0.25,
            ),
            call_count=3,
            priority_score=2.25,
        )

        output = StringIO()

        with (
            patch("annotation_prioritizer.cli.Console") as mock_console,
            patch("annotation_prioritizer.cli.analyze_file") as mock_analyze,
            patch("annotation_prioritizer.cli.display_results") as mock_display,
            patch("sys.argv", ["annotation-prioritizer", tmp.name]),
        ):
            test_console = Console(file=output, force_terminal=False, width=80)
            mock_console.return_value = test_console
            mock_analyze.return_value = (mock_priority,)

            main()

            mock_analyze.assert_called_once_with(tmp.name)
            mock_display.assert_called_once_with(test_console, (mock_priority,))


def test_main_with_min_calls_filter() -> None:
    """Test main() with min-calls filter."""
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as tmp:
        tmp.write("def test_func(): pass\n")
        tmp.flush()

        # Create mock data with low call count
        mock_priority = FunctionPriority(
            function_info=FunctionInfo(
                name="test_func",
                qualified_name="test_func",
                parameters=(),
                has_return_annotation=False,
                line_number=1,
                file_path=tmp.name,
            ),
            annotation_score=AnnotationScore(
                function_qualified_name="test_func",
                parameter_score=1.0,
                return_score=0.0,
                total_score=0.25,
            ),
            call_count=1,  # Low call count
            priority_score=0.75,
        )

        output = StringIO()

        with (
            patch("annotation_prioritizer.cli.Console") as mock_console,
            patch("annotation_prioritizer.cli.analyze_file") as mock_analyze,
            patch("annotation_prioritizer.cli.display_results") as mock_display,
            patch("sys.argv", ["annotation-prioritizer", tmp.name, "--min-calls", "5"]),
        ):
            test_console = Console(file=output, force_terminal=False, width=80)
            mock_console.return_value = test_console
            mock_analyze.return_value = (mock_priority,)

            main()

            mock_analyze.assert_called_once_with(tmp.name)
            # Should be called with empty tuple due to filtering
            mock_display.assert_called_once_with(test_console, ())


def test_main_analysis_error() -> None:
    """Test main() when analysis raises an exception."""
    with tempfile.NamedTemporaryFile(suffix=".py", mode="w", delete=False) as tmp:
        tmp.write("def test_func(): pass\n")
        tmp.flush()

        output = StringIO()
        test_console = Console(file=output, force_terminal=False, width=80)

        with (
            patch("annotation_prioritizer.cli.Console", return_value=test_console),
            patch("annotation_prioritizer.cli.analyze_file", side_effect=ValueError("Test error")),
            patch("sys.argv", ["annotation-prioritizer", tmp.name]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 1
        output_str = output.getvalue()
        assert "Error analyzing file" in output_str
        assert "Test error" in output_str


def test_main_directory_input() -> None:
    """Test main() with directory instead of file."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        output = StringIO()
        test_console = Console(file=output, force_terminal=False, width=80)

        with (
            patch("annotation_prioritizer.cli.Console", return_value=test_console),
            patch("sys.argv", ["annotation-prioritizer", tmp_dir]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main()

        assert exc_info.value.code == 1
        output_str = output.getvalue()
        assert "is not a file" in output_str
