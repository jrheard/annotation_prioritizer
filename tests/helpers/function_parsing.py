"""Helper functions for parsing AST in tests."""

from pathlib import Path

from annotation_prioritizer.ast_visitors.call_counter import count_function_calls
from annotation_prioritizer.ast_visitors.class_discovery import build_class_registry
from annotation_prioritizer.ast_visitors.function_parser import parse_function_definitions
from annotation_prioritizer.ast_visitors.parse_ast import parse_ast_from_file
from annotation_prioritizer.ast_visitors.variable_discovery import build_variable_registry
from annotation_prioritizer.models import CallCount, FunctionInfo, UnresolvableCall


def parse_functions_from_file(file_path: str) -> tuple[FunctionInfo, ...]:
    """Parse functions from a file with full AST and registry context."""
    path = Path(file_path)
    parse_result = parse_ast_from_file(path)
    if not parse_result:
        return ()

    tree, _ = parse_result
    class_registry = build_class_registry(tree)
    return parse_function_definitions(tree, path, class_registry)


def count_calls_from_file(
    file_path: str, known_functions: tuple[FunctionInfo, ...]
) -> tuple[tuple[CallCount, ...], tuple[UnresolvableCall, ...]]:
    """Count function calls from a file with full AST and registry context."""
    path = Path(file_path)
    parse_result = parse_ast_from_file(path)
    if not parse_result:
        return ((), ())

    tree, source_code = parse_result
    class_registry = build_class_registry(tree)
    variable_registry = build_variable_registry(tree, class_registry)

    return count_function_calls(tree, known_functions, class_registry, variable_registry, source_code)
