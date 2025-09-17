"""Tests for output module."""

from annotation_prioritizer.output import display_results, format_results_table, print_summary_stats
from tests.helpers.console import assert_console_contains, capture_console_output
from tests.helpers.factories import make_parameter, make_priority


def test_format_results_table_empty() -> None:
    """Test formatting empty results table."""
    table = format_results_table(())

    assert table.title == "Function Annotation Priority Analysis"
    assert len(table.columns) == 4
    assert len(table.rows) == 0


def test_format_results_table_with_data() -> None:
    """Test formatting results table with data including yellow annotation styling."""
    priority1 = make_priority(
        name="high_priority",
        parameters=(make_parameter("x"),),
        param_score=0.0,
        return_score=0.0,
        call_count=10,
        line_number=1,
        file_path="test.py",
        priority_score=10.0,
    )

    # This priority will have 60% annotation to test yellow styling
    priority2 = make_priority(
        name="medium_priority",
        parameters=(make_parameter("x", annotated=True),),
        param_score=1.0,
        return_score=0.0,
        call_count=5,
        line_number=2,
        file_path="test.py",
        priority_score=2.0,
    )

    table = format_results_table((priority1, priority2))

    assert table.title == "Function Annotation Priority Analysis"
    assert len(table.columns) == 4
    assert len(table.rows) == 2


def test_format_results_table_color_styling() -> None:
    """Test formatting results table with all color styling combinations."""
    # Low priority score (<2.0) and high annotation (>=80%) - both green
    priority1 = make_priority(
        name="low_priority_high_annotation",
        param_score=1.0,
        return_score=1.0,
        has_return_annotation=True,
        call_count=1,
        line_number=1,
        file_path="test.py",
        priority_score=0.1,  # Low priority for green styling
    )

    table = format_results_table((priority1,))

    assert table.title == "Function Annotation Priority Analysis"
    assert len(table.columns) == 4
    assert len(table.rows) == 1


def test_print_summary_stats_empty() -> None:
    """Test printing summary stats for empty results."""
    with capture_console_output() as (console, output):
        print_summary_stats(console, ())
        assert_console_contains(output, "No functions found to analyze.")


def test_print_summary_stats_all_annotated() -> None:
    """Test printing summary stats when all functions are fully annotated."""
    priority = make_priority(
        name="test_func",
        parameters=(make_parameter("x", annotated=True),),
        param_score=1.0,
        return_score=1.0,
        call_count=5,
        line_number=1,
        file_path="test.py",
        priority_score=0.0,
    )

    with capture_console_output() as (console, output):
        print_summary_stats(console, (priority,))
        assert_console_contains(
            output,
            "Total functions analyzed: 1",
            "Fully annotated functions: 1",
            "High priority functions (score ≥ 2.0): 0",
            "All functions are fully annotated!",
        )


def test_print_summary_stats_with_high_priority() -> None:
    """Test printing summary stats with high priority functions."""
    priority1 = make_priority(
        name="high_priority",
        param_score=1.0,
        return_score=0.0,
        call_count=10,
        line_number=1,
        file_path="test.py",
        priority_score=7.5,
    )

    priority2 = make_priority(
        name="low_priority",
        param_score=1.0,
        return_score=1.0,
        call_count=1,
        line_number=2,
        file_path="test.py",
        priority_score=0.0,
    )

    with capture_console_output() as (console, output):
        print_summary_stats(console, (priority1, priority2))
        assert_console_contains(
            output,
            "Total functions analyzed: 2",
            "Fully annotated functions: 1",
            "High priority functions (score ≥ 2.0): 1",
            "function(s) need attention.",
        )


def test_display_results_empty() -> None:
    """Test displaying empty results."""
    with capture_console_output() as (console, output):
        display_results(console, ())
        assert_console_contains(output, "No functions found to analyze.")


def test_display_results_with_data() -> None:
    """Test displaying results with data."""
    priority = make_priority(
        name="test_func",
        param_score=1.0,
        return_score=0.0,
        call_count=5,
        line_number=1,
        file_path="test.py",
        priority_score=3.75,
    )

    with capture_console_output() as (console, output):
        display_results(console, (priority,))
        # Should contain both table and summary
        assert_console_contains(
            output,
            "Function Annotation Priority Analysis",
            "Summary:",
            "Total functions analyzed: 1",
        )
