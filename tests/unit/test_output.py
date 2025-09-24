"""Tests for output module."""

from pathlib import Path

from annotation_prioritizer.models import UnresolvableCall
from annotation_prioritizer.output import (
    display_results,
    display_unresolvable_summary,
    format_results_table,
    print_summary_stats,
)
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
        "high_priority",
        param_score=0.0,
        return_score=0.0,
        call_count=10,
        parameters=(make_parameter("x"),),
        line_number=1,
        file_path=Path("test.py"),
    )

    # This priority will have 60% annotation to test yellow styling
    priority2 = make_priority(
        "medium_priority",
        param_score=1.0,
        return_score=0.0,
        call_count=5,
        parameters=(make_parameter("x", annotated=True),),
        line_number=2,
        file_path=Path("test.py"),
        # Explicitly set total score to 60%
        total_score=0.6,
        priority_score=2.0,  # 5 * (1 - 0.6)
    )

    table = format_results_table((priority1, priority2))

    assert table.title == "Function Annotation Priority Analysis"
    assert len(table.columns) == 4
    assert len(table.rows) == 2


def test_format_results_table_color_styling() -> None:
    """Test formatting results table with all color styling combinations."""
    # Low priority score (<2.0) and high annotation (>=80%) - both green
    priority1 = make_priority(
        "low_priority_high_annotation",
        param_score=1.0,
        return_score=1.0,
        call_count=1,
        line_number=1,
        file_path=Path("test.py"),
        has_return_annotation=True,
        # Explicitly set total score to 90%
        total_score=0.9,
        priority_score=0.1,  # 1 * (1 - 0.9)
    )

    # High priority score (>=5.0) - should be red
    priority2 = make_priority(
        "very_high_priority",
        param_score=0.0,
        return_score=0.0,
        call_count=10,
        line_number=2,
        file_path=Path("test.py"),
        total_score=0.0,
        priority_score=10.0,  # Very high priority
    )

    table = format_results_table((priority1, priority2))

    assert table.title == "Function Annotation Priority Analysis"
    assert len(table.columns) == 4
    assert len(table.rows) == 2


def test_print_summary_stats_empty() -> None:
    """Test printing summary stats for empty results."""
    with capture_console_output() as (console, output):
        print_summary_stats(console, ())
        assert_console_contains(output, "No functions found to analyze.")


def test_print_summary_stats_all_annotated() -> None:
    """Test printing summary stats when all functions are fully annotated."""
    priority = make_priority(
        "test_func",
        param_score=1.0,
        return_score=1.0,
        call_count=5,
        parameters=(make_parameter("x", annotated=True),),
        line_number=1,
        file_path=Path("test.py"),
        has_return_annotation=True,
        total_score=1.0,
        priority_score=0.0,  # 5 * (1 - 1.0)
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
        "high_priority",
        param_score=1.0,
        return_score=0.0,
        call_count=10,
        line_number=1,
        file_path=Path("test.py"),
        # Explicitly set total score to 0.25 and priority to 7.5
        total_score=0.25,
        priority_score=7.5,  # 10 * (1 - 0.25)
    )

    priority2 = make_priority(
        "low_priority",
        param_score=1.0,
        return_score=1.0,
        call_count=1,
        line_number=2,
        file_path=Path("test.py"),
        has_return_annotation=True,
        total_score=1.0,
        priority_score=0.0,  # 1 * (1 - 1.0)
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
        "test_func",
        param_score=1.0,
        return_score=0.0,
        call_count=5,
        line_number=1,
        file_path=Path("test.py"),
        # Explicitly set total score to 0.25 and priority to 3.75
        total_score=0.25,
        priority_score=3.75,  # 5 * (1 - 0.25)
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


def test_display_unresolvable_summary_empty() -> None:
    """Test displaying empty unresolvable summary."""
    with capture_console_output() as (console, output):
        display_unresolvable_summary(console, ())
        # Should display nothing when there are no unresolvable calls
        assert output.getvalue() == ""


def test_display_unresolvable_summary_with_few_calls() -> None:
    """Test displaying unresolvable summary with a few calls."""
    calls = (
        UnresolvableCall(
            line_number=10,
            call_text="processor.process_data()",
        ),
        UnresolvableCall(
            line_number=15,
            call_text="getattr(obj, 'method')()",
        ),
        UnresolvableCall(
            line_number=20,
            call_text="handlers['key']()",
        ),
    )

    with capture_console_output() as (console, output):
        display_unresolvable_summary(console, calls)
        assert_console_contains(
            output,
            "Warning: 3 unresolvable call(s) found",
            "Examples:",
            "Line 10:",
            "Line 15:",
            "Line 20:",
        )


def test_display_unresolvable_summary_with_many_calls() -> None:
    """Test displaying unresolvable summary with more than 5 calls."""
    calls = [
        UnresolvableCall(
            line_number=i + 1,
            # Note: call_text is now limited to 50 chars in call_counter.py
            call_text=f"call_{i}() with a very long text that should",
        )
        for i in range(8)
    ]

    with capture_console_output() as (console, output):
        display_unresolvable_summary(console, tuple(calls))
        assert_console_contains(
            output,
            "Warning: 8 unresolvable call(s) found",
            "Examples:",
            # Should show only first 5
            "Line 1:",
            "Line 2:",
            "Line 3:",
            "Line 4:",
            "Line 5:",
            # Should indicate there are more
            "... and 3 more",
        )
        # Should not show lines 6-8
        assert "Line 6:" not in output.getvalue()
        assert "Line 7:" not in output.getvalue()
        assert "Line 8:" not in output.getvalue()


def test_display_unresolvable_summary_mixed_types() -> None:
    """Test displaying unresolvable summary with various call types."""
    calls = (
        UnresolvableCall(line_number=1, call_text="eval('code')"),
        UnresolvableCall(line_number=2, call_text="eval('more')"),
        UnresolvableCall(line_number=3, call_text="obj.method()"),
        UnresolvableCall(line_number=4, call_text="a.b.c.d()"),
        UnresolvableCall(line_number=5, call_text="json.dumps()"),
        UnresolvableCall(line_number=6, call_text="import.func()"),
    )

    with capture_console_output() as (console, output):
        display_unresolvable_summary(console, calls)
        assert_console_contains(
            output,
            "Warning: 6 unresolvable call(s) found",
            # First 5 examples shown
            "Line 1:",
            "Line 2:",
            "Line 3:",
            "Line 4:",
            "Line 5:",
            "... and 1 more",
        )
