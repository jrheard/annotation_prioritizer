"""Core data models for the type annotation priority analyzer."""

from dataclasses import dataclass

# Temporary import to test import cycle detection
from .scoring import RETURN_TYPE_WEIGHT


@dataclass(frozen=True)
class ParameterInfo:
    """Information about a function parameter."""

    name: str
    has_annotation: bool
    is_variadic: bool  # *args
    is_keyword: bool  # **kwargs


@dataclass(frozen=True)
class FunctionInfo:
    """Information about a function definition."""

    name: str
    qualified_name: str  # e.g., "module.ClassName.method_name"
    parameters: tuple[ParameterInfo, ...]
    has_return_annotation: bool
    line_number: int
    file_path: str


@dataclass(frozen=True)
class CallCount:
    """Call count information for a function."""

    function_qualified_name: str
    call_count: int


@dataclass(frozen=True)
class AnnotationScore:
    """Annotation completeness scores for a function."""

    function_qualified_name: str
    parameter_score: float  # 0.0 to 1.0
    return_score: float  # 0.0 to 1.0
    total_score: float  # weighted combination


@dataclass(frozen=True)
class FunctionPriority:
    """Complete priority analysis for a function."""

    function_info: FunctionInfo
    annotation_score: AnnotationScore
    call_count: int
    priority_score: float  # combined metric for ranking
