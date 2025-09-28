"""Position-aware index for efficient name resolution (prototype).

This module provides a position-aware index that uses binary search to
efficiently resolve names based on their position in the source code,
correctly handling Python's shadowing semantics.
"""

import bisect
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass

from annotation_prioritizer.models import NameBinding, QualifiedName, make_qualified_name
from annotation_prioritizer.scope_tracker import ScopeStack


@dataclass(frozen=True)
class PositionIndex:
    """Efficient position-aware name resolution index (prototype).

    Structure: Dict[scope][name] -> sorted list of (line_number, binding)
    Uses binary search for O(log k) lookups where k is the number of
    redefinitions of a name (typically 1-5).
    """

    _index: Mapping[QualifiedName, dict[str, list[tuple[int, NameBinding]]]]

    def resolve(self, name: str, line: int, scope_stack: ScopeStack) -> NameBinding | None:
        """Resolve a name at a given position using binary search.

        Args:
            name: The name to resolve (e.g., "sqrt", "Counter")
            line: The line number where the name is used
            scope_stack: The scope stack at the point of use

        Returns:
            The binding that applies at this position, or None if unresolved
        """
        # Try each scope from innermost to outermost
        for i in range(len(scope_stack), -1, -1):
            current_scope_stack = scope_stack[:i] if i > 0 else ()

            # Build qualified name for the scope
            if not current_scope_stack or len(current_scope_stack) == 1:
                scope_qualified = make_qualified_name("__module__")
            else:
                scope_qualified = make_qualified_name(".".join(s.name for s in current_scope_stack))

            if scope_qualified in self._index and name in self._index[scope_qualified]:
                bindings = self._index[scope_qualified][name]

                # Binary search for the latest binding before this line
                # We want the rightmost binding with line_number < line
                idx = bisect.bisect_left(bindings, (line, None))

                if idx > 0:
                    # There's at least one binding before this line
                    _, binding = bindings[idx - 1]
                    return binding

        return None


def build_position_index(
    bindings: list[NameBinding],
    unresolved_variables: list[tuple[NameBinding, str]] | None = None,
) -> PositionIndex:
    """Build an efficient position-aware index from bindings.

    Args:
        bindings: List of all name bindings collected from the AST
        unresolved_variables: List of variables needing target resolution

    Returns:
        A PositionIndex for efficient name resolution
    """
    # Build the index structure
    index: dict[QualifiedName, dict[str, list[tuple[int, NameBinding]]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for binding in bindings:
        # Convert scope_stack to qualified name for indexing
        # For empty or module-only scope, use just the module name
        if not binding.scope_stack or len(binding.scope_stack) == 1:
            scope_name = make_qualified_name("__module__")
        else:
            # Build qualified name from the scope stack
            scope_name = make_qualified_name(".".join(s.name for s in binding.scope_stack))
        index[scope_name][binding.name].append((binding.line_number, binding))

    # Sort each name's bindings by line number for binary search
    for scope_dict in index.values():
        for binding_list in scope_dict.values():
            binding_list.sort(key=lambda x: x[0])

    # If we have unresolved variables, resolve their targets
    if unresolved_variables:
        import dataclasses
        from annotation_prioritizer.models import NameBindingKind

        # Create temporary index for resolution
        temp_index = PositionIndex(_index=dict(index))

        # Resolve variable targets
        resolved_bindings = []
        for binding in bindings:
            # Check if this binding is an unresolved variable
            is_unresolved = False
            for var_binding, target_name in unresolved_variables:
                if binding == var_binding:
                    is_unresolved = True
                    # Resolve what the target refers to
                    resolved = temp_index.resolve(
                        target_name,
                        binding.line_number,
                        binding.scope_stack
                    )

                    if resolved and resolved.kind == NameBindingKind.CLASS:
                        # Create new binding with resolved target_class
                        resolved_binding = dataclasses.replace(
                            binding,
                            target_class=resolved.qualified_name
                        )
                        resolved_bindings.append(resolved_binding)
                    else:
                        resolved_bindings.append(binding)
                    break

            if not is_unresolved:
                resolved_bindings.append(binding)

        # Rebuild index with resolved bindings
        index = defaultdict(lambda: defaultdict(list))
        for binding in resolved_bindings:
            if not binding.scope_stack or len(binding.scope_stack) == 1:
                scope_name = make_qualified_name("__module__")
            else:
                scope_name = make_qualified_name(".".join(s.name for s in binding.scope_stack))
            index[scope_name][binding.name].append((binding.line_number, binding))

        # Sort again
        for scope_dict in index.values():
            for binding_list in scope_dict.values():
                binding_list.sort(key=lambda x: x[0])

    return PositionIndex(_index=dict(index))
