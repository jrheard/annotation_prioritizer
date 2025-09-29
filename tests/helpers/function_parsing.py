"""Helper functions for parsing AST in tests."""

import ast
from pathlib import Path

from annotation_prioritizer.analyzer import analyze_ast
from annotation_prioritizer.ast_visitors.call_counter import count_function_calls
from annotation_prioritizer.ast_visitors.function_parser import parse_function_definitions
from annotation_prioritizer.ast_visitors.name_binding_collector import NameBindingCollector
from annotation_prioritizer.ast_visitors.parse_ast import parse_ast_from_file, parse_ast_from_source
from annotation_prioritizer.models import (
    AnalysisResult,
    CallCount,
    FunctionInfo,
    NameBindingKind,
    PositionIndex,
    QualifiedName,
    UnresolvableCall,
    build_position_index,
)


def parse_functions_from_file(file_path: Path) -> tuple[FunctionInfo, ...]:
    """Parse functions from a file with full AST and position index."""
    parse_result = parse_ast_from_file(file_path)
    if not parse_result:
        return ()

    tree, source_code = parse_result
    _, position_index, _ = build_position_index_from_source(source_code)
    return parse_function_definitions(tree, file_path, position_index)


def build_position_index_from_source(
    source: str,
) -> tuple[ast.Module, PositionIndex, set[QualifiedName]]:
    """Build position index and known classes from source code.

    Args:
        source: Python source code as a string

    Returns:
        Tuple of (tree, position_index, known_classes)
    """
    tree = ast.parse(source)

    # Collect all name bindings in a single pass
    collector = NameBindingCollector()
    collector.visit(tree)

    # Build position-aware index with resolved variable targets
    position_index = build_position_index(collector.bindings, collector.unresolved_variables)

    # Extract known classes for __init__ resolution
    known_classes = {
        binding.qualified_name
        for binding in collector.bindings
        if binding.kind == NameBindingKind.CLASS and binding.qualified_name
    }

    return tree, position_index, known_classes


def count_calls_from_file(
    file_path: Path, known_functions: tuple[FunctionInfo, ...]
) -> tuple[tuple[CallCount, ...], tuple[UnresolvableCall, ...]]:
    """Count function calls from a file using position-aware resolution."""
    parse_result = parse_ast_from_file(file_path)
    if not parse_result:
        return ((), ())

    tree, source_code = parse_result

    _, position_index, known_classes = build_position_index_from_source(source_code)

    return count_function_calls(tree, known_functions, position_index, known_classes, source_code)


def parse_functions_from_source(source: str) -> tuple[FunctionInfo, ...]:
    """Parse functions from source code string with full AST and position index.

    Useful for tests that need to verify function discovery including synthetic __init__.

    Args:
        source: Python source code as a string

    Returns:
        Tuple of FunctionInfo objects
    """
    tree = ast.parse(source)
    file_path = Path("test.py")
    _, position_index, _ = build_position_index_from_source(source)
    return parse_function_definitions(tree, file_path, position_index)


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
