"""Annotation completeness scoring system."""

from .models import AnnotationScore, FunctionInfo, ParameterInfo

# Weight constants for scoring components
RETURN_TYPE_WEIGHT = 0.25
PARAMETERS_WEIGHT = 0.75


def calculate_parameter_score(parameters: tuple[ParameterInfo, ...]) -> float:
    """Calculate 0.0-1.0 score for parameter annotations.

    Args:
        parameters: Tuple of parameter information

    Returns:
        Score from 0.0 (no parameters annotated) to 1.0 (all parameters annotated).
        Returns 1.0 if there are no parameters (fully annotated by definition).

    """
    if not parameters:
        return 1.0  # No parameters = fully annotated

    annotated_count = sum(1 for p in parameters if p.has_annotation)
    return annotated_count / len(parameters)


def calculate_return_score(*, has_return_annotation: bool) -> float:
    """Calculate 0.0-1.0 score for return annotation.

    Args:
        has_return_annotation: Whether the function has a return type annotation

    Returns:
        1.0 if annotated, 0.0 if not annotated.

    """
    return 1.0 if has_return_annotation else 0.0


def calculate_annotation_score(function_info: FunctionInfo) -> AnnotationScore:
    """Calculate annotation completeness score with weighted components.

    Uses a weighted scoring system where:
    - Parameter annotations contribute 75% of the total score
    - Return annotation contributes 25% of the total score

    Args:
        function_info: Function information to score

    Returns:
        AnnotationScore with parameter, return, and total scores.

    """
    parameter_score = calculate_parameter_score(function_info.parameters)
    return_score = calculate_return_score(has_return_annotation=function_info.has_return_annotation)

    total_score = PARAMETERS_WEIGHT * parameter_score + RETURN_TYPE_WEIGHT * return_score

    return AnnotationScore(
        function_qualified_name=function_info.qualified_name,
        parameter_score=parameter_score,
        return_score=return_score,
        total_score=total_score,
    )
