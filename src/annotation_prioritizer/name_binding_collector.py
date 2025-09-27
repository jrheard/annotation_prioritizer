"""Single-pass AST visitor that collects all name bindings (prototype).

This is a prototype implementation for testing the position-aware resolution
approach to fix the shadowing bug (issue #31).
"""

import ast

from annotation_prioritizer.models import NameBinding, NameBindingKind
from annotation_prioritizer.scope_tracker import (
    Scope,
    ScopeKind,
    ScopeStack,
    add_scope,
    build_qualified_name,
    create_initial_stack,
    drop_last_scope,
)


class NameBindingCollector(ast.NodeVisitor):
    """Single-pass collector of all name bindings in the AST (prototype)."""

    def __init__(self) -> None:
        """Initialize the collector."""
        self.bindings: list[NameBinding] = []
        self._scope_stack: ScopeStack = create_initial_stack()

    def visit_Import(self, node: ast.Import) -> None:
        """Track module imports like 'import math'."""
        for alias in node.names:
            binding = NameBinding(
                name=alias.asname or alias.name,
                line_number=node.lineno,
                kind=NameBindingKind.IMPORT,
                qualified_name=None,  # Unresolvable in Phase 1
                scope_stack=self._scope_stack,
                source_module=alias.name,  # Track for Phase 2
            )
            self.bindings.append(binding)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Track from imports like 'from math import sqrt'."""
        module = node.module or ""  # Handle relative imports
        for alias in node.names:
            if alias.name == "*":
                # Star imports - we can't track individual names
                continue
            binding = NameBinding(
                name=alias.asname or alias.name,
                line_number=node.lineno,
                kind=NameBindingKind.IMPORT,
                qualified_name=None,  # Unresolvable in Phase 1
                scope_stack=self._scope_stack,
                source_module=module,  # Track source for Phase 2
            )
            self.bindings.append(binding)
        self.generic_visit(node)

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Track function definitions."""
        qualified = build_qualified_name(self._scope_stack, node.name)
        binding = NameBinding(
            name=node.name,
            line_number=node.lineno,
            kind=NameBindingKind.FUNCTION,
            qualified_name=qualified,
            scope_stack=self._scope_stack,
            source_module=None,
        )
        self.bindings.append(binding)

        # Continue traversal with updated scope
        self._scope_stack = add_scope(self._scope_stack, Scope(ScopeKind.FUNCTION, node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Track async function definitions."""
        qualified = build_qualified_name(self._scope_stack, node.name)
        binding = NameBinding(
            name=node.name,
            line_number=node.lineno,
            kind=NameBindingKind.FUNCTION,
            qualified_name=qualified,
            scope_stack=self._scope_stack,
            source_module=None,
        )
        self.bindings.append(binding)

        # Continue traversal with updated scope
        self._scope_stack = add_scope(self._scope_stack, Scope(ScopeKind.FUNCTION, node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track class definitions."""
        qualified = build_qualified_name(self._scope_stack, node.name)
        binding = NameBinding(
            name=node.name,
            line_number=node.lineno,
            kind=NameBindingKind.CLASS,
            qualified_name=qualified,
            scope_stack=self._scope_stack,
            source_module=None,
        )
        self.bindings.append(binding)

        # Continue traversal with class scope
        self._scope_stack = add_scope(self._scope_stack, Scope(ScopeKind.CLASS, node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)
