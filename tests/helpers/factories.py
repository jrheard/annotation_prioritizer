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
    """Create ParameterInfo with short syntax.

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
        name: Function name (default: "test_func")
        qualified_name: Fully qualified name (default: "__module__.{name}")
        parameters: Tuple of ParameterInfo objects (default: empty tuple)
        has_return_annotation: Whether function has return type annotation
        line_number: Line number where function is defined
        file_path: Path to the source file

    Returns:
        FunctionInfo instance with the specified attributes
    """
    if qualified_name is None:
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


def make_annotation_score(
    function_name: str = "test_func",
    *,
    parameter_score: float = 0.0,
    return_score: float = 0.0,
    # Default weights from scoring module
    parameter_weight: float = 0.6,
    return_weight: float = 0.4,
) -> AnnotationScore:
    """Create AnnotationScore with automatic total calculation.

    Args:
        function_name: Function name for qualified name
        parameter_score: Score for parameter annotations (0.0 to 1.0)
        return_score: Score for return annotation (0.0 or 1.0)
        parameter_weight: Weight for parameter score in total
        return_weight: Weight for return score in total

    Returns:
        AnnotationScore instance with calculated total score
    """
    qualified_name = function_name if "__module__" in function_name else f"__module__.{function_name}"
    total_score = parameter_score * parameter_weight + return_score * return_weight

    return AnnotationScore(
        function_qualified_name=qualified_name,
        parameter_score=parameter_score,
        return_score=return_score,
        total_score=total_score,
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
    qualified_name: str | None = None,
    has_return_annotation: bool | None = None,
    # Weights for score calculation
    parameter_weight: float = 0.6,
    return_weight: float = 0.4,
) -> FunctionPriority:
    """Create FunctionPriority with automatic score calculation.

    Args:
        name: Function name
        param_score: Score for parameter annotations (0.0 to 1.0)
        return_score: Score for return annotation (0.0 or 1.0)
        call_count: Number of times function is called
        parameters: Tuple of ParameterInfo objects (default: empty tuple)
        file_path: Path to the source file
        line_number: Line number where function is defined
        qualified_name: Fully qualified name (default: "__module__.{name}")
        has_return_annotation: Override for return annotation status
        parameter_weight: Weight for parameter score in total
        return_weight: Weight for return score in total

    Returns:
        FunctionPriority instance with nested objects and calculated scores
    """
    if qualified_name is None:
        qualified_name = f"__module__.{name}"
    if parameters is None:
        parameters = ()

    # Determine has_return_annotation if not explicitly provided
    if has_return_annotation is None:
        has_return_annotation = return_score > 0

    # Create nested objects
    function_info = FunctionInfo(
        name=name,
        qualified_name=qualified_name,
        parameters=parameters,
        has_return_annotation=has_return_annotation,
        line_number=line_number,
        file_path=file_path,
    )

    # Calculate total annotation score
    total_score = param_score * parameter_weight + return_score * return_weight

    annotation_score = AnnotationScore(
        function_qualified_name=qualified_name,
        parameter_score=param_score,
        return_score=return_score,
        total_score=total_score,
    )

    # Calculate priority score: higher score means the function needs annotation more urgently.
    # Uses the formula where priority is inversely proportional to annotation completeness.
    priority_score = call_count * (1 - total_score)

    return FunctionPriority(
        function_info=function_info,
        annotation_score=annotation_score,
        call_count=call_count,
        priority_score=priority_score,
    )
