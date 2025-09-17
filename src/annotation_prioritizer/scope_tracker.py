"""Scope tracking utilities for AST traversal.

This module provides utilities for tracking scope context during AST traversal,
enabling proper resolution of qualified names for functions, classes, and methods.
All functions are pure and work with immutable data structures.

Key Components:
    - Pure scope stack functions: add_scope, drop_last_scope, create_initial_stack
    - Name resolution functions: generate_name_candidates, build_qualified_name
    - Helper functions: get_containing_class, in_class, in_function

The scope tracking is used by multiple AST visitors throughout the codebase to
consistently build qualified names like "__module__.ClassName.method_name".
"""

import ast
from collections.abc import Set as AbstractSet

from annotation_prioritizer.models import Scope, ScopeKind

type ScopeStack = tuple[Scope, ...]


def create_initial_stack() -> ScopeStack:
    """Create an initial scope stack with just the module scope.

    TODO: when we support multiple files, should we replace __module__ with foo/bar/baz.py?

    Returns:
        Initial stack containing only the module scope
    """
    return (Scope(kind=ScopeKind.MODULE, name="__module__"),)


def add_scope(stack: ScopeStack, scope: Scope) -> ScopeStack:
    """Add a new scope onto the scope state.

    This is a pure function that returns a new stack rather than
    modifying the input stack.

    Args:
        stack: Current scope stack (not modified)
        scope: The scope to add (class or function)

    Returns:
        New stack with the scope appended
    """
    return (*stack, scope)


def drop_last_scope(stack: ScopeStack) -> ScopeStack:
    """Return a new stack without the last scope.

    Args:
        stack: Current scope stack

    Returns:
        New stack with the top scope removed

    Raises:
        AssertionError: If attempting to remove the root module scope
    """
    assert len(stack) > 1, "Cannot pop module scope"
    return stack[:-1]


def get_current_scope(stack: ScopeStack) -> Scope:
    """Get the current (innermost) scope.

    Args:
        stack: Current scope stack

    Returns:
        The scope at the top of the stack
    """
    return stack[-1]


def get_containing_class(stack: ScopeStack) -> str | None:
    """Get the qualified name of the containing class, if any.

    Args:
        stack: Current scope stack

    Returns:
        Qualified class name if inside a class, None otherwise
    """
    for i in range(len(stack) - 1, -1, -1):
        if stack[i].kind == ScopeKind.CLASS:
            return ".".join(s.name for s in stack[: i + 1])
    return None


def in_class(stack: ScopeStack) -> bool:
    """Check if currently inside a class definition.

    Args:
        stack: Current scope stack

    Returns:
        True if any scope in the stack is a class
    """
    return any(s.kind == ScopeKind.CLASS for s in stack)


def in_function(stack: ScopeStack) -> bool:
    """Check if currently inside a function definition.

    Args:
        stack: Current scope stack

    Returns:
        True if any scope in the stack is a function
    """
    return any(s.kind == ScopeKind.FUNCTION for s in stack)


def generate_name_candidates(scope_stack: ScopeStack, name: str) -> tuple[str, ...]:
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
    for i in range(len(scope_stack) - 1, -1, -1):
        prefix = ".".join(s.name for s in scope_stack[: i + 1])
        candidates.append(f"{prefix}.{name}")

    return tuple(candidates)


def build_qualified_name(
    scope_stack: ScopeStack, name: str, exclude_kinds: frozenset[ScopeKind] | None = None
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
    else:
        # If we hit something that's not a Name or Attribute, we have an incomplete chain
        # This could happen with expressions like foo()[0].bar or (a + b).method
        assert isinstance(current, ast.Name), (
            f"Expected ast.Name at base of attribute chain, got {type(current).__name__}. "
            "Complex expressions like foo()[0].bar are not currently supported."
        )

    return tuple(parts)
