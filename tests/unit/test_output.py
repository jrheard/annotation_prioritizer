"""Tests for output module."""

from io import StringIO

from rich.console import Console

from annotation_prioritizer.models import AnnotationScore, FunctionInfo, FunctionPriority, ParameterInfo
from annotation_prioritizer.output import display_results, format_results_table, print_summary_stats


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
    output = StringIO()
    console = Console(file=output, force_terminal=False, width=80)

    print_summary_stats(console, ())

    output_str = output.getvalue()
    assert "No functions found to analyze." in output_str


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

    output = StringIO()
    console = Console(file=output, force_terminal=False, width=80)

    print_summary_stats(console, (priority,))

    output_str = output.getvalue()
    assert "Total functions analyzed: 1" in output_str
    assert "Fully annotated functions: 1" in output_str
    assert "High priority functions (score ≥ 2.0): 0" in output_str
    assert "All functions are fully annotated!" in output_str


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

    output = StringIO()
    console = Console(file=output, force_terminal=False, width=80)

    print_summary_stats(console, (priority1, priority2))

    output_str = output.getvalue()
    assert "Total functions analyzed: 2" in output_str
    assert "Fully annotated functions: 1" in output_str
    assert "High priority functions (score ≥ 2.0): 1" in output_str
    assert "function(s) need attention." in output_str


def test_display_results_empty() -> None:
    """Test displaying empty results."""
    output = StringIO()
    console = Console(file=output, force_terminal=False, width=80)

    display_results(console, ())

    output_str = output.getvalue()
    assert "No functions found to analyze." in output_str


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

    output = StringIO()
    console = Console(file=output, force_terminal=False, width=80)

    display_results(console, (priority,))

    output_str = output.getvalue()
    # Should contain both table and summary
    assert "Function Annotation Priority Analysis" in output_str
    assert "Summary:" in output_str
    assert "Total functions analyzed: 1" in output_str
