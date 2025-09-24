"""Helper functions for parsing AST in tests."""

from pathlib import Path

from annotation_prioritizer.ast_visitors.class_discovery import build_class_registry
from annotation_prioritizer.ast_visitors.function_parser import parse_function_definitions
from annotation_prioritizer.ast_visitors.parse_ast import parse_ast_from_file
from annotation_prioritizer.models import FunctionInfo


def parse_functions_from_file(file_path: str) -> tuple[FunctionInfo, ...]:
    """Parse functions from a file with full AST and registry context."""
    path = Path(file_path)
    parse_result = parse_ast_from_file(path)
    if not parse_result:
        return ()

    tree, _ = parse_result
    class_registry = build_class_registry(tree)
    return parse_function_definitions(tree, path, class_registry)
