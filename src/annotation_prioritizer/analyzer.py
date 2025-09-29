"""Main analysis orchestrator for type annotation prioritization."""

import ast
from pathlib import Path

from annotation_prioritizer.ast_visitors.call_counter import count_function_calls
from annotation_prioritizer.ast_visitors.function_parser import parse_function_definitions
from annotation_prioritizer.ast_visitors.name_binding_collector import NameBindingCollector
from annotation_prioritizer.ast_visitors.parse_ast import parse_ast_from_file
from annotation_prioritizer.models import (
    AnalysisResult,
    AnnotationScore,
    FunctionPriority,
    NameBindingKind,
    QualifiedName,
    build_position_index,
)
from annotation_prioritizer.scoring import calculate_annotation_score


def calculate_priority_score(annotation_score: AnnotationScore, call_count: int) -> float:
    """Combine annotation completeness and call frequency into priority score.

    Higher priority = more calls + less annotated.
    Priority = call_count * (1.0 - annotation_score.total_score)
    """
    return call_count * (1.0 - annotation_score.total_score)


def analyze_ast(tree: ast.Module, source_code: str, filename: str = "test.py") -> AnalysisResult:
    """Complete analysis pipeline for a parsed AST.

    Args:
        tree: Parsed AST module
        source_code: Python source code as a string
        filename: Filename to use for the analysis (affects qualified names)

    Returns:
        AnalysisResult with function priorities sorted by priority score
        (highest first) and all unresolvable calls.
    """
    file_path_obj = Path(filename)

    # 1. Collect all name bindings in a single pass
    collector = NameBindingCollector()
    collector.visit(tree)

    # 2. Build position-aware index with resolved variable targets
    position_index = build_position_index(collector.bindings, collector.unresolved_variables)

    # 3. Extract known classes for __init__ resolution
    known_classes = {
        binding.qualified_name
        for binding in collector.bindings
        if binding.kind == NameBindingKind.CLASS and binding.qualified_name
    }

    # 4. Parse function definitions (kept separate for detailed parameter info)
    function_infos = parse_function_definitions(tree, file_path_obj, position_index)

    if not function_infos:
        return AnalysisResult(priorities=(), unresolvable_calls=())

    # 5. Count function calls with position-aware resolution
    resolved_counts, unresolvable_calls = count_function_calls(
        tree, function_infos, position_index, known_classes, source_code
    )
    call_count_map: dict[QualifiedName, int] = {
        cc.function_qualified_name: cc.call_count for cc in resolved_counts
    }

    # 6. Calculate annotation scores and combine into priority rankings
    priorities: list[FunctionPriority] = []
    for func_info in function_infos:
        annotation_score = calculate_annotation_score(func_info)
        call_count = call_count_map.get(func_info.qualified_name, 0)
        priority_score = calculate_priority_score(annotation_score, call_count)

        priority = FunctionPriority(
            function_info=func_info,
            annotation_score=annotation_score,
            call_count=call_count,
            priority_score=priority_score,
        )
        priorities.append(priority)

    # 7. Sort by priority score (highest first) and return complete result
    sorted_priorities = tuple(sorted(priorities, key=lambda p: p.priority_score, reverse=True))
    return AnalysisResult(priorities=sorted_priorities, unresolvable_calls=unresolvable_calls)


def analyze_file(file_path: str) -> AnalysisResult:
    """Complete analysis pipeline for a single Python file.

    Returns AnalysisResult with function priorities sorted by priority score
    (highest first) and all unresolvable calls.
    """
    file_path_obj = Path(file_path)

    parse_result = parse_ast_from_file(file_path_obj)
    if not parse_result:
        return AnalysisResult(priorities=(), unresolvable_calls=())

    tree, source_code = parse_result
    return analyze_ast(tree, source_code, str(file_path_obj))
