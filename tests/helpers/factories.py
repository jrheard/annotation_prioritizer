"""Factory functions for creating test model objects with sensible defaults.

These factories reduce boilerplate in tests and make them more maintainable
by providing convenient shortcuts for creating model objects.
"""

from annotation_prioritizer.models import AnnotationScore, FunctionInfo, FunctionPriority, ParameterInfo


def make_parameter(
    name: str = "param",
    *,
    annotated: bool = False,
    variadic: bool = False,
    keyword: bool = False,
) -> ParameterInfo:
    """Create ParameterInfo with short syntax.

    Args:
        name: Parameter name
        annotated: Whether parameter has annotation (maps to has_annotation)
        variadic: Whether parameter is *args
        keyword: Whether parameter is **kwargs

    Returns:
        ParameterInfo instance
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
        qualified_name: Full qualified name (defaults to __module__.{name})
        parameters: Tuple of parameters (defaults to empty tuple)
        has_return_annotation: Whether function has return type annotation
        line_number: Line number where function is defined
        file_path: Path to source file

    Returns:
        FunctionInfo instance
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
    param_score: float = 0.0,
    return_score: float = 0.0,
    total_score: float | None = None,
) -> AnnotationScore:
    """Create AnnotationScore with automatic total calculation if not provided.

    Args:
        function_name: Function name (used to build qualified name)
        param_score: Parameter annotation score (0.0 to 1.0)
        return_score: Return annotation score (0.0 or 1.0)
        total_score: Total score (auto-calculated if None using 0.75 param, 0.25 return weights)

    Returns:
        AnnotationScore instance
    """
    if not function_name.startswith("__module__."):
        qualified_name = f"__module__.{function_name}"
    else:
        qualified_name = function_name

    if total_score is None:
        # Using standard weights from scoring module
        total_score = param_score * 0.75 + return_score * 0.25

    return AnnotationScore(
        function_qualified_name=qualified_name,
        parameter_score=param_score,
        return_score=return_score,
        total_score=total_score,
    )


def make_priority(  # noqa: PLR0913
    name: str = "test_func",
    *,
    param_score: float = 0.0,
    return_score: float = 0.0,
    call_count: int = 0,
    has_return_annotation: bool | None = None,
    parameters: tuple[ParameterInfo, ...] | None = None,
    file_path: str = "/test.py",
    line_number: int = 1,
    priority_score: float | None = None,
) -> FunctionPriority:
    """Create FunctionPriority with automatic score calculation.

    Builds nested FunctionInfo and AnnotationScore automatically.

    Args:
        name: Function name
        param_score: Parameter annotation score
        return_score: Return annotation score
        call_count: Number of times function is called
        has_return_annotation: Whether has return annotation (inferred from return_score if None)
        parameters: Function parameters (defaults to empty tuple)
        file_path: Path to source file
        line_number: Line number where function is defined
        priority_score: Final priority score (auto-calculated if None)

    Returns:
        FunctionPriority instance
    """
    # Infer has_return_annotation from return_score if not provided
    if has_return_annotation is None:
        has_return_annotation = return_score > 0

    if parameters is None:
        parameters = ()

    # Calculate total annotation score with standard weights
    total_annotation_score = param_score * 0.75 + return_score * 0.25

    # Create nested objects
    function_info = make_function_info(
        name=name,
        parameters=parameters,
        has_return_annotation=has_return_annotation,
        line_number=line_number,
        file_path=file_path,
    )

    annotation_score = make_annotation_score(
        function_name=name,
        param_score=param_score,
        return_score=return_score,
        total_score=total_annotation_score,
    )

    # Calculate priority score if not provided using the standard formula
    if priority_score is None:
        priority_score = call_count * (1 - total_annotation_score)

    return FunctionPriority(
        function_info=function_info,
        annotation_score=annotation_score,
        call_count=call_count,
        priority_score=priority_score,
    )
