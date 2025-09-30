"""Position-aware name resolution for Python code analysis.

This module provides efficient position-aware name resolution using binary search
to mirror Python's lexical scoping rules.

Design Rationale - Why Two-Level Dictionary Structure:
    Name resolution looks up UNQUALIFIED local names (e.g., "sqrt") from specific
    scopes, not qualified names. When resolving a name reference, we know:
    - The local name being referenced (e.g., "sqrt")
    - The current scope (e.g., "__module__.Calculator.add")
    - The line number where it's used

    But we DON'T know the qualified name of the binding we're looking for. We must
    search through the scope chain to discover which binding the name refers to.

    The two-level structure enables lookups like:
        index[scope_qualified_name][local_name] -> list of bindings

    An alternative structure like dict[QualifiedName, list[LineBinding]] would index
    by the binding's full qualified name, but that doesn't help during resolution
    since we only have the unqualified name.

Performance:
    The PositionIndex enables O(log k) lookup of the most recent binding before a
    given line number, where k is the number of bindings for a given name in a scope.
"""

import bisect
import dataclasses
from collections import defaultdict
from collections.abc import Mapping

from annotation_prioritizer.models import (
    NameBinding,
    NameBindingKind,
    QualifiedName,
    ScopeStack,
)
from annotation_prioritizer.scope_tracker import scope_stack_to_qualified_name

type LineBinding = tuple[int, NameBinding]
"""A name binding at a specific line number.

Used in PositionIndex for binary search: the int is the line number where
the binding occurs, and the NameBinding contains the binding information.
These are kept sorted by line number for efficient lookup.
"""


type PositionIndex = Mapping[QualifiedName, Mapping[str, list[LineBinding]]]
"""Position-aware name resolution index.

Structure:
    Mapping[QualifiedName, dict[str, list[LineBinding]]]

    - Outer dict key (QualifiedName): Which scope contains the bindings
      Examples: "__module__", "__module__.Calculator"

    - Inner dict key (str): Local name within that scope
      Examples: "sqrt", "Calculator", "add", "math"

    - Value (list[LineBinding]): All bindings for that name in that scope,
      sorted by line number for binary search

Example for this code:
    import math                  # line 1

    class Calculator:            # line 5
        def add(self, a, b):     # line 6
            return a + b
        def multiply(self, a, b): # line 9
            return a * b

    {
        "__module__": {
            "math": [(1, NameBinding(..., kind=IMPORT))],
            "Calculator": [(5, NameBinding(..., kind=CLASS))]
        },
        "__module__.Calculator": {
            "add": [(6, NameBinding(..., kind=FUNCTION))],
            "multiply": [(9, NameBinding(..., kind=FUNCTION))]
        }
    }
"""

# Mutable version of PositionIndex used internally during construction
type _MutablePositionIndex = dict[QualifiedName, dict[str, list[LineBinding]]]


def resolve_name(index: PositionIndex, name: str, line: int, scope_stack: ScopeStack) -> NameBinding | None:
    """Resolve a name at a given position using binary search.

    Searches through the scope chain from innermost to outermost scope,
    finding the most recent binding of the given name that occurs before
    the specified line number.

    Args:
        index: The position index to search in
        name: The name to resolve (e.g., "sqrt", "Calculator")
        line: The line number where the name is used (1-indexed)
        scope_stack: The scope context where the name appears

    Returns:
        The most recent NameBinding for this name before the given line,
        or None if no binding is found in any scope.

    Raises:
        ValueError: If scope_stack is empty
    """
    if not scope_stack:
        msg = "scope_stack must not be empty"
        raise ValueError(msg)

    # Try each scope from innermost to outermost
    for scope_depth in range(len(scope_stack), 0, -1):
        # Build scope qualified name for this depth
        current_scope = scope_stack[:scope_depth]
        scope_name = scope_stack_to_qualified_name(current_scope)

        # Look up bindings for this name in this scope
        if scope_name not in index:
            continue

        scope_dict = index[scope_name]
        if name not in scope_dict:
            continue

        bindings = scope_dict[name]

        # Use binary search to find the latest binding before this line
        # We search for bindings with line_number < line (strictly less than)
        idx = bisect.bisect_left(bindings, line, key=lambda x: x[0])

        if idx > 0:
            return bindings[idx - 1][1]

    return None


def _build_index_structure(
    bindings: list[NameBinding],
) -> _MutablePositionIndex:
    """Build the internal index structure from bindings."""
    index: _MutablePositionIndex = defaultdict(lambda: defaultdict(list))

    for binding in bindings:
        scope_name = scope_stack_to_qualified_name(binding.scope_stack)
        index[scope_name][binding.name].append((binding.line_number, binding))

    # Sort each name's bindings by line number for binary search
    for scope_dict in index.values():
        for binding_list in scope_dict.values():
            binding_list.sort(key=lambda x: x[0])

    return index


def _resolve_variable_target(
    binding: NameBinding, target_name: str, temp_index: PositionIndex
) -> NameBinding:
    """Resolve a variable's target class using the temporary index."""
    resolved = resolve_name(temp_index, target_name, binding.line_number, binding.scope_stack)

    if resolved and resolved.kind == NameBindingKind.CLASS:
        # Create NEW binding with resolved target_class
        return dataclasses.replace(binding, target_class=resolved.qualified_name)

    # Couldn't resolve or not a class - keep original
    return binding


def _resolve_all_variables(
    bindings: list[NameBinding],
    unresolved_variables: list[tuple[NameBinding, str]],
    temp_index: PositionIndex,
) -> list[NameBinding]:
    """Resolve all unresolved variables and return the complete list of bindings."""
    unresolved_map = dict(unresolved_variables)

    resolved_bindings: list[NameBinding] = []
    for binding in bindings:
        if binding in unresolved_map:
            resolved_bindings.append(_resolve_variable_target(binding, unresolved_map[binding], temp_index))
        else:
            resolved_bindings.append(binding)

    return resolved_bindings


def build_position_index(
    bindings: list[NameBinding],
    unresolved_variables: list[tuple[NameBinding, str]] | None = None,
) -> PositionIndex:
    """Build an efficient position-aware index from bindings and resolve variable targets.

    This factory function creates a PositionIndex from collected name bindings. It uses
    a two-phase resolution approach to handle variable assignments that reference other
    names (e.g., calc = Calculator()):

    Phase 1: Build basic index from all bindings (with unresolved variable targets)
    Phase 2: Use that index to resolve variable targets, then rebuild with complete bindings

    This ensures all variable targets are correctly resolved based on position-aware
    shadowing rules.

    Args:
        bindings: List of all name bindings collected from AST traversal
        unresolved_variables: Optional list of (binding, target_name) tuples for
            variables that reference other names. If provided, these will be resolved
            using position-aware lookup.

    Returns:
        A PositionIndex with resolved bindings, ready for efficient O(log k) lookup
    """
    # Phase 1: Build the basic index
    index = _build_index_structure(bindings)

    # Phase 2: If we have unresolved variables, resolve their targets and rebuild
    if unresolved_variables:
        resolved_bindings = _resolve_all_variables(bindings, unresolved_variables, index)
        index = _build_index_structure(resolved_bindings)

    return index
