"""Variable type registry and tracking utilities.

This module provides data models and utilities for tracking variable-to-type
mappings across different scopes in Python code.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from annotation_prioritizer.models import QualifiedName
from annotation_prioritizer.scope_tracker import ScopeStack, resolve_name_in_scope


@dataclass(frozen=True)
class VariableType:
    """Type information for a variable.

    Tracks what type a variable has been assigned or annotated with.
    The is_instance flag distinguishes between class references and instances.
    """

    # TODO: This version of VariableType is limited - only handles Class vs Instance distinction.
    # Real Python code has many other patterns: None values, callables (functions/lambdas),
    # modules, generics (List[T], Dict[K,V]), unions (T | None), etc.
    # Consider replacing with discriminated union/enum with variants for each type category.

    class_name: QualifiedName  # e.g., "__module__.Calculator"
    is_instance: bool  # True for calc = Calculator(), False for calc = Calculator


@dataclass(frozen=True)
class VariableRegistry:
    """Registry of variable types keyed by scope-qualified names.

    Example keys:
    - Module-level: "__module__.variable_name"
    - Function-level: "__module__.function_name.variable_name"
    - Method-level: "__module__.ClassName.method_name.variable_name"
    """

    variables: Mapping[QualifiedName, VariableType]


def lookup_variable(
    registry: VariableRegistry, scope_stack: ScopeStack, variable_name: str
) -> VariableType | None:
    """Look up a variable's type, checking parent scopes.

    Finds variables with proper Python scoping rules (inner shadows outer).

    Args:
        registry: Variable registry to search
        scope_stack: Current scope context for resolution
        variable_name: Variable name to look up

    Returns:
        Variable type if found in any accessible scope, None otherwise
    """
    key = resolve_name_in_scope(scope_stack, variable_name, registry.variables.keys())
    return registry.variables.get(key) if key else None
