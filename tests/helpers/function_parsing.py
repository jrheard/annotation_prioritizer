"""Helper functions for parsing AST in tests."""

import ast
from pathlib import Path

from annotation_prioritizer.analyzer import analyze_ast
from annotation_prioritizer.ast_visitors.call_counter import count_function_calls
from annotation_prioritizer.ast_visitors.class_discovery import ClassRegistry, build_class_registry
from annotation_prioritizer.ast_visitors.function_parser import parse_function_definitions
from annotation_prioritizer.ast_visitors.parse_ast import parse_ast_from_file, parse_ast_from_source
from annotation_prioritizer.ast_visitors.variable_discovery import VariableRegistry, build_variable_registry
from annotation_prioritizer.models import (
    AnalysisResult,
    CallCount,
    FunctionInfo,
    QualifiedName,
    UnresolvableCall,
)


def parse_functions_from_file(file_path: Path) -> tuple[FunctionInfo, ...]:
    """Parse functions from a file with full AST and registry context."""
    parse_result = parse_ast_from_file(file_path)
    if not parse_result:
        return ()

    tree, _ = parse_result
    class_registry = build_class_registry(tree)
    return parse_function_definitions(tree, file_path, class_registry)


def count_calls_from_file(
    file_path: Path, known_functions: tuple[FunctionInfo, ...]
) -> tuple[tuple[CallCount, ...], tuple[UnresolvableCall, ...]]:
    """Count function calls from a file with full AST and registry context."""
    parse_result = parse_ast_from_file(file_path)
    if not parse_result:
        return ((), ())

    tree, source_code = parse_result
    class_registry = build_class_registry(tree)
    variable_registry = build_variable_registry(tree, class_registry)

    return count_function_calls(tree, known_functions, class_registry, variable_registry, source_code)


def parse_functions_from_source(source: str) -> tuple[FunctionInfo, ...]:
    """Parse functions from source code string with full AST and registry context.

    Useful for tests that need to verify function discovery including synthetic __init__.

    Args:
        source: Python source code as a string

    Returns:
        Tuple of FunctionInfo objects
    """
    tree = ast.parse(source)
    file_path = Path("test.py")
    class_registry = build_class_registry(tree)
    return parse_function_definitions(tree, file_path, class_registry)


def analyze_source(source_code: str) -> AnalysisResult:
    """Complete analysis pipeline for Python source code.

    Args:
        source_code: Python source code as a string
        filename: Filename to use for the analysis (affects qualified names)

    Returns:
        AnalysisResult with function priorities sorted by priority score
        (highest first) and all unresolvable calls.
    """
    filename = "<test source code>"
    parse_result = parse_ast_from_source(source_code, filename)
    if not parse_result:
        return AnalysisResult(priorities=(), unresolvable_calls=())

    tree, _ = parse_result
    return analyze_ast(tree, source_code, filename)


def count_calls_from_source(source: str) -> dict[QualifiedName, int]:
    """Count function calls in source code and return as dict.

    Args:
        source: Python source code as a string

    Returns:
        Dict mapping function qualified names to call counts
    """
    result = analyze_source(source)

    # Convert priorities to dict for easier assertions
    return {priority.function_info.qualified_name: priority.call_count for priority in result.priorities}


def build_registries_from_source(source: str) -> tuple[ast.Module, ClassRegistry, VariableRegistry]:
    """Parse source code and build both class and variable registries.

    Args:
        source: Python source code as a string

    Returns:
        Tuple of (AST tree, class registry, variable registry)
    """
    tree = ast.parse(source)
    class_registry = build_class_registry(tree)
    variable_registry = build_variable_registry(tree, class_registry)
    return tree, class_registry, variable_registry
