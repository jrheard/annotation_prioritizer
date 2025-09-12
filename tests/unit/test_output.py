"""Tests for output module."""

from annotation_prioritizer.models import AnnotationScore, FunctionInfo, FunctionPriority, ParameterInfo
from annotation_prioritizer.output import display_results, format_results_table, print_summary_stats
from tests.helpers.console import assert_console_contains, capture_console_output


def test_format_results_table_empty() -> None:
    """Test formatting empty results table."""
    table = format_results_table(())

    assert table.title == "Function Annotation Priority Analysis"
    assert len(table.columns) == 4
    assert len(table.rows) == 0


def test_format_results_table_with_data() -> None:
    """Test formatting results table with data including yellow annotation styling."""
    priority1 = FunctionPriority(
        function_info=FunctionInfo(
            name="high_priority",
            qualified_name="high_priority",
            parameters=(ParameterInfo("x", False, False, False),),
            has_return_annotation=False,
            line_number=1,
            file_path="test.py",
        ),
        annotation_score=AnnotationScore(
            function_qualified_name="high_priority",
            parameter_score=0.0,
            return_score=0.0,
            total_score=0.0,
        ),
        call_count=10,
        priority_score=10.0,
    )

    # This priority will have 60% annotation to test yellow styling
    priority2 = FunctionPriority(
        function_info=FunctionInfo(
            name="medium_priority",
            qualified_name="medium_priority",
            parameters=(ParameterInfo("x", True, False, False),),
            has_return_annotation=False,
            line_number=2,
            file_path="test.py",
        ),
        annotation_score=AnnotationScore(
            function_qualified_name="medium_priority",
            parameter_score=1.0,
            return_score=0.0,
            total_score=0.6,  # 60% annotation for yellow styling
        ),
        call_count=5,
        priority_score=2.0,
    )

    table = format_results_table((priority1, priority2))

    assert table.title == "Function Annotation Priority Analysis"
    assert len(table.columns) == 4
    assert len(table.rows) == 2


def test_format_results_table_color_styling() -> None:
    """Test formatting results table with all color styling combinations."""
    # Low priority score (<2.0) and high annotation (>=80%) - both green
    priority1 = FunctionPriority(
        function_info=FunctionInfo(
            name="low_priority_high_annotation",
            qualified_name="low_priority_high_annotation",
            parameters=(),
            has_return_annotation=True,
            line_number=1,
            file_path="test.py",
        ),
        annotation_score=AnnotationScore(
            function_qualified_name="low_priority_high_annotation",
            parameter_score=1.0,
            return_score=1.0,
            total_score=0.9,  # 90% annotation for green styling
        ),
        call_count=1,
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
    priority = FunctionPriority(
        function_info=FunctionInfo(
            name="test_func",
            qualified_name="test_func",
            parameters=(ParameterInfo("x", True, False, False),),
            has_return_annotation=True,
            line_number=1,
            file_path="test.py",
        ),
        annotation_score=AnnotationScore(
            function_qualified_name="test_func",
            parameter_score=1.0,
            return_score=1.0,
            total_score=1.0,
        ),
        call_count=5,
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
    priority1 = FunctionPriority(
        function_info=FunctionInfo(
            name="high_priority",
            qualified_name="high_priority",
            parameters=(),
            has_return_annotation=False,
            line_number=1,
            file_path="test.py",
        ),
        annotation_score=AnnotationScore(
            function_qualified_name="high_priority",
            parameter_score=1.0,
            return_score=0.0,
            total_score=0.25,
        ),
        call_count=10,
        priority_score=7.5,
    )

    priority2 = FunctionPriority(
        function_info=FunctionInfo(
            name="low_priority",
            qualified_name="low_priority",
            parameters=(),
            has_return_annotation=True,
            line_number=2,
            file_path="test.py",
        ),
        annotation_score=AnnotationScore(
            function_qualified_name="low_priority",
            parameter_score=1.0,
            return_score=1.0,
            total_score=1.0,
        ),
        call_count=1,
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
    priority = FunctionPriority(
        function_info=FunctionInfo(
            name="test_func",
            qualified_name="test_func",
            parameters=(),
            has_return_annotation=False,
            line_number=1,
            file_path="test.py",
        ),
        annotation_score=AnnotationScore(
            function_qualified_name="test_func",
            parameter_score=1.0,
            return_score=0.0,
            total_score=0.25,
        ),
        call_count=5,
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
