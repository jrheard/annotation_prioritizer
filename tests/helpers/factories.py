"""Factory functions for creating test model objects.

This module provides factory functions to simplify the creation of model
objects in tests, reducing duplication and improving readability.
"""

from pathlib import Path

from annotation_prioritizer.models import (
    AnnotationScore,
    FunctionInfo,
    FunctionPriority,
    NameBinding,
    NameBindingKind,
    ParameterInfo,
    QualifiedName,
    Scope,
    ScopeKind,
    ScopeStack,
    make_qualified_name,
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
    qualified_name: QualifiedName | None = None,
    parameters: tuple[ParameterInfo, ...] | None = None,
    has_return_annotation: bool = False,
    line_number: int = 1,
    file_path: Path | None = None,
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
        qualified_name = make_qualified_name(f"__module__.{name}")
    if parameters is None:
        parameters = ()
    if file_path is None:
        file_path = Path("/test.py")

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
    file_path: Path | None = None,
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
    qualified_name = make_qualified_name(f"__module__.{name}")
    if parameters is None:
        parameters = ()

    # Use explicit values or defaults
    if total_score is None:
        total_score = 0.0
    if priority_score is None:
        priority_score = 0.0
    if file_path is None:
        file_path = Path("/test.py")

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


def make_module_scope() -> ScopeStack:
    """Create a module-level scope stack.

    Returns:
        A scope stack containing only the module scope
    """
    return (Scope(ScopeKind.MODULE, "__module__"),)


def make_function_scope(func_name: str) -> ScopeStack:
    """Create a function scope stack within module scope.

    Args:
        func_name: Name of the function

    Returns:
        A scope stack with module and function scopes
    """
    return (
        Scope(ScopeKind.MODULE, "__module__"),
        Scope(ScopeKind.FUNCTION, func_name),
    )


def make_class_scope(class_name: str) -> ScopeStack:
    """Create a class scope stack within module scope.

    Args:
        class_name: Name of the class

    Returns:
        A scope stack with module and class scopes
    """
    return (
        Scope(ScopeKind.MODULE, "__module__"),
        Scope(ScopeKind.CLASS, class_name),
    )


def make_import_binding(
    name: str,
    source_module: str,
    *,
    line_number: int = 1,
    scope_stack: ScopeStack | None = None,
) -> NameBinding:
    """Create an import NameBinding with sensible defaults.

    Args:
        name: Local name being imported (e.g., "sqrt")
        source_module: Module being imported from (e.g., "math")
        line_number: Line where import occurs (default: 1)
        scope_stack: Scope where binding occurs (default: module scope)

    Returns:
        NameBinding instance for an import
    """
    if scope_stack is None:
        scope_stack = make_module_scope()

    return NameBinding(
        name=name,
        line_number=line_number,
        kind=NameBindingKind.IMPORT,
        qualified_name=None,  # Imports don't have qualified names
        scope_stack=scope_stack,
        source_module=source_module,
        target_class=None,
    )


def make_class_binding(
    name: str,
    *,
    line_number: int = 1,
    scope_stack: ScopeStack | None = None,
    qualified_name: QualifiedName | None = None,
) -> NameBinding:
    """Create a class NameBinding with sensible defaults.

    Args:
        name: Class name (e.g., "Calculator")
        line_number: Line where class is defined (default: 1)
        scope_stack: Scope where binding occurs (default: module scope)
        qualified_name: Fully qualified name (default: auto-generated from scope and name)

    Returns:
        NameBinding instance for a class definition
    """
    if scope_stack is None:
        scope_stack = make_module_scope()

    if qualified_name is None:
        qualified_name = make_qualified_name(f"__module__.{name}")

    return NameBinding(
        name=name,
        line_number=line_number,
        kind=NameBindingKind.CLASS,
        qualified_name=qualified_name,
        scope_stack=scope_stack,
        source_module=None,
        target_class=None,
    )


def make_function_binding(
    name: str,
    *,
    line_number: int = 1,
    scope_stack: ScopeStack | None = None,
    qualified_name: QualifiedName | None = None,
) -> NameBinding:
    """Create a function NameBinding with sensible defaults.

    Args:
        name: Function name (e.g., "process")
        line_number: Line where function is defined (default: 1)
        scope_stack: Scope where binding occurs (default: module scope)
        qualified_name: Fully qualified name (default: auto-generated from scope and name)

    Returns:
        NameBinding instance for a function definition
    """
    if scope_stack is None:
        scope_stack = make_module_scope()

    if qualified_name is None:
        qualified_name = make_qualified_name(f"__module__.{name}")

    return NameBinding(
        name=name,
        line_number=line_number,
        kind=NameBindingKind.FUNCTION,
        qualified_name=qualified_name,
        scope_stack=scope_stack,
        source_module=None,
        target_class=None,
    )


def make_variable_binding(
    name: str,
    *,
    line_number: int = 1,
    scope_stack: ScopeStack | None = None,
    target_class: QualifiedName | None = None,
    qualified_name: QualifiedName | None = None,
) -> NameBinding:
    """Create a variable NameBinding with sensible defaults.

    Args:
        name: Variable name (e.g., "calc")
        line_number: Line where variable is assigned (default: 1)
        scope_stack: Scope where binding occurs (default: module scope)
        target_class: Class the variable is an instance of (default: None)
        qualified_name: Fully qualified name (default: auto-generated from scope and name)

    Returns:
        NameBinding instance for a variable assignment
    """
    if scope_stack is None:
        scope_stack = make_module_scope()

    if qualified_name is None:
        qualified_name = make_qualified_name(f"__module__.{name}")

    return NameBinding(
        name=name,
        line_number=line_number,
        kind=NameBindingKind.VARIABLE,
        qualified_name=qualified_name,
        scope_stack=scope_stack,
        source_module=None,
        target_class=target_class,
    )
