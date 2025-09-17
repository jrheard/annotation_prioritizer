"""Main analysis orchestrator for type annotation prioritization."""

from .call_counter import count_function_calls
from .function_parser import parse_function_definitions
from .models import AnnotationScore, FunctionPriority, QualifiedName
from .scoring import calculate_annotation_score


def calculate_priority_score(annotation_score: AnnotationScore, call_count: int) -> float:
    """Combine annotation completeness and call frequency into priority score.

    Higher priority = more calls + less annotated.
    Priority = call_count * (1.0 - annotation_score.total_score)
    """
    return call_count * (1.0 - annotation_score.total_score)


def analyze_file(file_path: str) -> tuple[FunctionPriority, ...]:
    """Complete analysis pipeline for a single Python file.

    Returns function priorities sorted by priority score (highest first).
    """
    # 1. Parse function definitions
    function_infos = parse_function_definitions(file_path)

    if not function_infos:
        return ()

    # 2. Count function calls
    call_counts = count_function_calls(file_path, function_infos)
    call_count_map: dict[QualifiedName, int] = {
        cc.function_qualified_name: cc.call_count for cc in call_counts
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

    # 4. Sort by priority score (highest first)
    return tuple(sorted(priorities, key=lambda p: p.priority_score, reverse=True))
