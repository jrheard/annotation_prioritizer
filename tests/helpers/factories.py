"""Factory functions for creating test model objects.

This module provides factory functions to simplify the creation of model
objects in tests, reducing duplication and improving readability.
"""

from annotation_prioritizer.models import (
    AnnotationScore,
    FunctionInfo,
    FunctionPriority,
    ParameterInfo,
)


def make_parameter(
    name: str = "param",
    *,
    annotated: bool = False,
    variadic: bool = False,
    keyword: bool = False,
) -> ParameterInfo:
    """Create ParameterInfo with sensible defaults.

    Args:
        name: Parameter name (default: "param")
        annotated: Whether the parameter has a type annotation
        variadic: Whether this is a *args parameter
        keyword: Whether this is a **kwargs parameter

    Returns:
        ParameterInfo instance with the specified attributes
    """
    return ParameterInfo(
        name=name,
        has_annotation=annotated,
        is_variadic=variadic,
        is_keyword=keyword,
    )


def make_function_info(  # noqa: PLR0913
    name: str = "test_func",
    *,
    qualified_name: str | None = None,
    parameters: tuple[ParameterInfo, ...] | None = None,
    has_return_annotation: bool = False,
    line_number: int = 1,
    file_path: str = "/test.py",
) -> FunctionInfo:
    """Create FunctionInfo with sensible defaults.

    Args:
        name: Function name
        qualified_name: Fully qualified name (if None, defaults to "__module__.{name}")
        parameters: Tuple of ParameterInfo objects (default: empty tuple)
        has_return_annotation: Whether function has return type annotation
        line_number: Line number where function is defined
        file_path: Path to the source file

    Returns:
        FunctionInfo instance with the specified attributes
    """
    if qualified_name is None:
        # Only check for dots if we're auto-generating the qualified name
        assert "." not in name, (
            f"Function name should not be qualified when qualified_name is not provided, got: {name}"
        )
        qualified_name = f"__module__.{name}"
    if parameters is None:
        parameters = ()

    return FunctionInfo(
        name=name,
        qualified_name=qualified_name,
        parameters=parameters,
        has_return_annotation=has_return_annotation,
        line_number=line_number,
        file_path=file_path,
    )


def make_priority(  # noqa: PLR0913
    name: str = "test_func",
    *,
    param_score: float = 0.0,
    return_score: float = 0.0,
    call_count: int = 0,
    parameters: tuple[ParameterInfo, ...] | None = None,
    file_path: str = "/test.py",
    line_number: int = 1,
    has_return_annotation: bool = False,
    total_score: float | None = None,
    priority_score: float | None = None,
) -> FunctionPriority:
    """Create FunctionPriority with sensible defaults.

    Args:
        name: Function name (not a qualified name)
        param_score: Score for parameter annotations (0.0 to 1.0)
        return_score: Score for return annotation (0.0 or 1.0)
        call_count: Number of times function is called
        parameters: Tuple of ParameterInfo objects (default: empty tuple)
        file_path: Path to the source file
        line_number: Line number where function is defined
        has_return_annotation: Whether function has return type annotation
        total_score: Total annotation score (if None, defaults to 0.0)
        priority_score: Priority score (if None, defaults to 0.0)

    Returns:
        FunctionPriority instance with nested objects
    """
    # Ensure name is not already qualified
    assert "." not in name, f"Function name should not be qualified, got: {name}"

    # Ensure consistency between return_score and has_return_annotation
    assert (return_score == 0.0 and not has_return_annotation) or (
        return_score == 1.0 and has_return_annotation
    ), (
        f"Inconsistent return annotation state: return_score={return_score}, "
        f"has_return_annotation={has_return_annotation}"
    )
    qualified_name = f"__module__.{name}"
    if parameters is None:
        parameters = ()

    # Use explicit values or defaults
    if total_score is None:
        total_score = 0.0
    if priority_score is None:
        priority_score = 0.0

    # Create nested objects
    function_info = FunctionInfo(
        name=name,
        qualified_name=qualified_name,
        parameters=parameters,
        has_return_annotation=has_return_annotation,
        line_number=line_number,
        file_path=file_path,
    )

    annotation_score = AnnotationScore(
        function_qualified_name=qualified_name,
        parameter_score=param_score,
        return_score=return_score,
        total_score=total_score,
    )

    return FunctionPriority(
        function_info=function_info,
        annotation_score=annotation_score,
        call_count=call_count,
        priority_score=priority_score,
    )
