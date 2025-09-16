"""Scope tracking utilities for AST traversal.

This module provides utilities for tracking scope context during AST traversal,
enabling proper resolution of qualified names for functions, classes, and methods.
The design combines a stateful ScopeState class for convenient traversal with
pure functions for name resolution logic.

Key Components:
    - ScopeState: Mutable class that maintains the scope stack during traversal
    - Pure helper functions: Generate candidates and resolve names without side effects

The scope tracking is used by multiple AST visitors throughout the codebase to
consistently build qualified names like "__module__.ClassName.method_name".
"""

import ast
from collections.abc import Set as AbstractSet

from annotation_prioritizer.models import Scope, ScopeKind


class ScopeState:
    """Mutable scope state that tracks traversal context during AST walking.

    Maintains a stack of scopes (module, class, function) that represents the
    current position in the AST. Always starts with a module scope that cannot
    be popped.

    Usage:
        state = ScopeState()
        state.push(Scope(kind=ScopeKind.CLASS, name="MyClass"))
        qualified = build_qualified_name(state.stack, "method")  # "__module__.MyClass.method"
        state.pop()
    """

    def __init__(self) -> None:
        """Initialize with module scope as the root."""
        super().__init__()
        self._stack: list[Scope] = [Scope(kind=ScopeKind.MODULE, name="__module__")]

    def push(self, scope: Scope) -> None:
        """Push a new scope onto the stack.

        Args:
            scope: The scope to enter (class or function)
        """
        self._stack.append(scope)

    def pop(self) -> None:
        """Pop the top scope from the stack.

        Raises:
            AssertionError: If attempting to pop the root module scope
        """
        assert len(self._stack) > 1, "Cannot pop module scope"
        self._stack.pop()

    @property
    def stack(self) -> tuple[Scope, ...]:
        """Get immutable view of current stack for use with pure functions.

        Returns:
            Current scope stack as an immutable tuple
        """
        return tuple(self._stack)

    @property
    def current_scope(self) -> Scope:
        """Get the current (innermost) scope.

        Returns:
            The scope at the top of the stack
        """
        return self._stack[-1]

    def get_containing_class(self) -> str | None:
        """Get the qualified name of the containing class, if any.

        Returns:
            Qualified class name if inside a class, None otherwise
        """
        for i in range(len(self._stack) - 1, -1, -1):
            if self._stack[i].kind == ScopeKind.CLASS:
                return ".".join(s.name for s in self._stack[: i + 1])
        return None

    def in_class(self) -> bool:
        """Check if currently inside a class definition.

        Returns:
            True if any scope in the stack is a class
        """
        return any(s.kind == ScopeKind.CLASS for s in self._stack)

    def in_function(self) -> bool:
        """Check if currently inside a function definition.

        Returns:
            True if any scope in the stack is a function
        """
        return any(s.kind == ScopeKind.FUNCTION for s in self._stack)


def generate_name_candidates(scope_stack: tuple[Scope, ...], name: str) -> tuple[str, ...]:
    """Generate all possible qualified names from innermost to outermost scope.

    Matches Python's name resolution order where inner scopes shadow outer scopes.
    This function is used for both class and function name resolution.

    Args:
        scope_stack: Current scope context from ScopeState
        name: The name to qualify (can be simple like "foo" or compound like "Outer.Inner")

    Returns:
        Tuple of candidate qualified names from most to least specific

    Example:
        With scope stack [MODULE("__module__"), CLASS("Outer"), FUNCTION("method")]:
        generate_name_candidates(stack, "Helper") returns:
        ("__module__.Outer.method.Helper",
         "__module__.Outer.Helper",
         "__module__.Helper")
    """
    candidates: list[str] = []

    # Work from innermost to outermost (backwards through stack)
    # Skip index 0 since that's always the MODULE scope
    for i in range(len(scope_stack) - 1, 0, -1):
        prefix = ".".join(s.name for s in scope_stack[: i + 1])
        candidates.append(f"{prefix}.{name}")

    # Module level as final fallback
    candidates.append(f"__module__.{name}")
    return tuple(candidates)


def build_qualified_name(
    scope_stack: tuple[Scope, ...], name: str, exclude_kinds: frozenset[ScopeKind] | None = None
) -> str:
    """Build a qualified name from scope stack with optional filtering.

    Used primarily for self.method() resolution where we need to exclude
    function scopes to get the containing class.

    Args:
        scope_stack: Current scope context from ScopeState
        name: The name to qualify
        exclude_kinds: Scope kinds to exclude from the path

    Returns:
        Qualified name with filtered scope path

    Example:
        With stack [MODULE, CLASS("Calculator"), FUNCTION("helper"), name="add"]:
        build_qualified_name(stack, "add", exclude_kinds={FUNCTION})
        returns "__module__.Calculator.add"
    """
    exclude_kinds = exclude_kinds or frozenset()
    filtered = [s.name for s in scope_stack if s.kind not in exclude_kinds]
    return ".".join([*filtered, name])


def find_first_match(candidates: tuple[str, ...], registry: AbstractSet[str]) -> str | None:
    """Check candidates against a registry and return first match.

    Simple helper that iterates through candidates and returns the first
    one found in the registry. Used by resolution methods to check against
    known classes or functions.

    Args:
        candidates: Qualified name candidates to check
        registry: Set of known names to match against

    Returns:
        First matching candidate or None if no matches
    """
    for candidate in candidates:
        if candidate in registry:
            return candidate
    return None


def extract_attribute_chain(node: ast.Attribute) -> tuple[str, ...]:
    """Extract the chain of attributes from nested ast.Attribute nodes.

    Handles expressions like Outer.Inner.method by walking up the AST
    to extract all parts of the chain.

    Args:
        node: The ast.Attribute node to extract from

    Returns:
        Tuple of names from the attribute chain

    Example:
        For Outer.Inner.method, returns ("Outer", "Inner", "method")
    """
    parts: list[str] = [node.attr]
    current = node.value

    while isinstance(current, ast.Attribute):
        parts.insert(0, current.attr)
        current = current.value

    if isinstance(current, ast.Name):
        parts.insert(0, current.id)

    return tuple(parts)
