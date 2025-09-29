"""Scope tracking utilities for AST traversal.

This module provides utilities for tracking scope context during AST traversal,
enabling proper resolution of qualified names for functions, classes, and methods.
All functions are pure and work with immutable data structures.

Key Components:
    - Pure scope stack functions: add_scope, drop_last_scope, create_initial_stack
    - Name resolution functions: _generate_name_candidates, build_qualified_name

The scope tracking is used by multiple AST visitors throughout the codebase to
consistently build qualified names like "__module__.ClassName.method_name".
"""

import ast
from collections.abc import Iterable

from annotation_prioritizer.iteration import first
from annotation_prioritizer.models import QualifiedName, Scope, ScopeKind, ScopeStack, make_qualified_name


def create_initial_stack() -> ScopeStack:
    """Create an initial scope stack with just the module scope.

    TODO: when we support multiple files, should we replace __module__ with foo/bar/baz.py?

    Returns:
        Initial stack containing only the module scope
    """
    return (Scope(kind=ScopeKind.MODULE, name="__module__"),)


def add_scope(stack: ScopeStack, scope: Scope) -> ScopeStack:
    """Add a new scope onto the scope state.

    TODO: Keep an eye on perf, strongly consider just making ScopeStack
    mutable and turning these functions into methods. It's fine.

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


def scope_stack_to_qualified_name(scope_stack: ScopeStack) -> QualifiedName:
    """Convert a scope stack to its qualified name for indexing.

    Module scope is represented as "__module__", and nested scopes are joined with dots.
    This is used for position-aware name resolution indexing.

    Args:
        scope_stack: The scope stack to convert

    Returns:
        A QualifiedName suitable for use as an index key
    """
    if not scope_stack or len(scope_stack) == 1:
        return make_qualified_name("__module__")
    return make_qualified_name(".".join(s.name for s in scope_stack))


def _generate_name_candidates(scope_stack: ScopeStack, name: str) -> tuple[QualifiedName, ...]:
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
        _generate_name_candidates(stack, "Helper") returns:
        ("__module__.Outer.method.Helper",
         "__module__.Outer.Helper",
         "__module__.Helper")
    """
    candidates: list[QualifiedName] = []

    # Work from innermost to outermost (backwards through stack)
    for i in range(len(scope_stack) - 1, -1, -1):
        prefix = ".".join(s.name for s in scope_stack[: i + 1])
        candidates.append(make_qualified_name(f"{prefix}.{name}"))

    return tuple(candidates)


def build_qualified_name(scope_stack: ScopeStack, name: str) -> QualifiedName:
    """Build a qualified name from scope stack and name.

    Combines the scope hierarchy with a name to create a fully qualified name.
    This is the standard way to build qualified names from scope context.

    Args:
        scope_stack: Current scope context from ScopeState (must not be empty)
        name: Name to append to the scope path

    Returns:
        A validated QualifiedName instance

    Raises:
        ValueError: If scope_stack is empty or name is invalid

    Example:
        >>> stack = (Scope(MODULE, "__module__"), Scope(CLASS, "Calculator"))
        >>> build_qualified_name(stack, "add")
        QualifiedName("__module__.Calculator.add")
    """
    if not scope_stack:
        msg = "Cannot build qualified name from empty scope stack"
        raise ValueError(msg)

    if not name or not name.strip():
        msg = f"Name cannot be empty or whitespace: {name!r}"
        raise ValueError(msg)

    parts = [s.name for s in scope_stack]
    parts.append(name)

    return make_qualified_name(".".join(parts))


def get_containing_class_qualified_name(scope_stack: ScopeStack) -> QualifiedName | None:
    """Get the qualified name of the containing class from the scope stack.

    Searches backward through the scope stack to find the first class scope,
    then builds the qualified name from all scopes up to and including that class.

    Args:
        scope_stack: Current scope context

    Returns:
        Qualified name of the containing class, or None if not in a class context

    Example:
        With scope stack [MODULE("__module__"), CLASS("Outer"), FUNCTION("method")]:
        Returns "__module__.Outer"
    """
    for scope in reversed(scope_stack):
        if scope.kind == ScopeKind.CLASS:
            # Build qualified name from all scopes up to and including this class
            class_parts: list[str] = []
            for s in scope_stack:
                class_parts.append(s.name)
                if s == scope:
                    break
            return make_qualified_name(".".join(class_parts))
    return None


def resolve_name_in_scope(
    scope_stack: ScopeStack, name: str, registry: Iterable[QualifiedName]
) -> QualifiedName | None:
    """Resolve a name to its qualified form by checking scope levels.

    Generates candidates from innermost to outermost scope and returns the first match
    found in the registry. This function supports Python's name resolution order where
    inner scopes shadow outer scopes.

    Args:
        scope_stack: Current scope context
        name: The name to resolve (e.g., "Calculator", "add")
        registry: Collection of qualified names to check against

    Returns:
        Qualified name if found in registry, None otherwise

    Example:
        With scope stack [MODULE("__module__"), CLASS("Outer")] and name "Inner":
        - Generates candidates: "__module__.Outer.Inner", "__module__.Inner"
        - Returns the first candidate that exists in the registry
    """
    candidates = _generate_name_candidates(scope_stack, name)
    return first(candidates, lambda c: c in registry)


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
