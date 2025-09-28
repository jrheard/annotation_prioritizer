"""Main analysis orchestrator for type annotation prioritization."""

import ast
from pathlib import Path

from annotation_prioritizer.ast_visitors.call_counter import count_function_calls
from annotation_prioritizer.ast_visitors.class_discovery import build_class_registry
from annotation_prioritizer.ast_visitors.function_parser import parse_function_definitions
from annotation_prioritizer.ast_visitors.import_discovery import build_import_registry
from annotation_prioritizer.ast_visitors.parse_ast import parse_ast_from_file
from annotation_prioritizer.ast_visitors.variable_discovery import build_variable_registry
from annotation_prioritizer.models import (
    AnalysisResult,
    AnnotationScore,
    CallCount,
    FunctionPriority,
    NameBindingKind,
    QualifiedName,
)

# Prototype imports for position-aware resolution
from annotation_prioritizer.name_binding_collector import NameBindingCollector
from annotation_prioritizer.position_index import build_position_index
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

    # Build all registries upfront
    class_registry = build_class_registry(tree)
    variable_registry = build_variable_registry(tree, class_registry)
    import_registry = build_import_registry(tree)

    # 1. Parse function definitions with class registry
    function_infos = parse_function_definitions(tree, file_path_obj, class_registry)

    if not function_infos:
        return AnalysisResult(priorities=(), unresolvable_calls=())

    # 2. Count function calls with all dependencies
    resolved_counts, unresolvable_calls = count_function_calls(
        tree, function_infos, class_registry, variable_registry, import_registry, source_code
    )
    call_count_map: dict[QualifiedName, int] = {
        cc.function_qualified_name: cc.call_count for cc in resolved_counts
    }

    # 3. Calculate annotation scores and combine into priority rankings
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

    # 4. Sort by priority score (highest first) and return complete result
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


def analyze_ast_prototype(tree: ast.Module, source_code: str, filename: str = "test.py") -> AnalysisResult:
    """Prototype analysis pipeline using position-aware resolution.

    This is a simplified version for testing the single collector architecture
    and position-aware resolution to fix the shadowing bug.
    """
    from annotation_prioritizer.call_counter_prototype import CallCountVisitorPrototype

    file_path_obj = Path(filename)

    # Single collection pass (replaces 5 separate visitors)
    collector = NameBindingCollector()
    collector.visit(tree)

    # Build position-aware index with variable resolution
    position_index = build_position_index(collector.bindings, collector.unresolved_variables)

    # Extract known classes from the bindings
    known_classes = {
        binding.qualified_name
        for binding in collector.bindings
        if binding.kind == NameBindingKind.CLASS and binding.qualified_name
    }

    # Parse function definitions (using existing implementation)
    # We still need ClassRegistry for now since FunctionDefinitionVisitor uses it
    class_registry = build_class_registry(tree)
    function_infos = parse_function_definitions(tree, file_path_obj, class_registry)

    if not function_infos:
        return AnalysisResult(priorities=(), unresolvable_calls=())

    # Count function calls with position-aware resolution
    visitor = CallCountVisitorPrototype(function_infos, position_index, source_code)
    visitor.set_known_classes(known_classes)
    visitor.visit(tree)

    # Build CallCount objects from visitor results
    call_counts = tuple(
        CallCount(function_qualified_name=func_name, call_count=count)
        for func_name, count in visitor.call_counts.items()
    )

    # Calculate annotation scores for all functions
    annotation_scores = tuple(calculate_annotation_score(func) for func in function_infos)

    # Create priority analysis for each function
    priorities = []
    for func_info in function_infos:
        # Find matching call count
        call_count = next(
            (cc.call_count for cc in call_counts if cc.function_qualified_name == func_info.qualified_name), 0
        )

        # Find matching annotation score
        annotation_score = next(
            score for score in annotation_scores if score.function_qualified_name == func_info.qualified_name
        )

        priority_score = calculate_priority_score(annotation_score, call_count)

        priorities.append(
            FunctionPriority(
                function_info=func_info,
                annotation_score=annotation_score,
                call_count=call_count,
                priority_score=priority_score,
            )
        )

    # Sort by priority score (highest first)
    sorted_priorities = tuple(sorted(priorities, key=lambda p: p.priority_score, reverse=True))

    return AnalysisResult(priorities=sorted_priorities, unresolvable_calls=tuple(visitor._unresolvable_calls))
