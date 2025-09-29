"""Single-pass collector of all name bindings in the AST.

This visitor collects all name bindings (imports, functions, classes, variables)
in a single AST traversal, tracking their positions and scope context. This enables
position-aware name resolution that correctly handles Python's shadowing semantics.
"""

import ast
from typing import override

from annotation_prioritizer.models import NameBinding, NameBindingKind, Scope, ScopeKind, ScopeStack
from annotation_prioritizer.scope_tracker import add_scope, create_initial_stack, drop_last_scope


class NameBindingCollector(ast.NodeVisitor):
    """Single-pass collector of all name bindings in the AST.

    Collects imports, function definitions, class definitions, and variable
    assignments while tracking their scope context and line numbers. This data
    is used to build a PositionIndex for efficient position-aware name resolution.

    Attributes:
        bindings: List of all name bindings found during traversal
        unresolved_variables: List of (binding, target_name) tuples for variables
            that reference other names (e.g., calc = Calculator())
    """

    def __init__(self) -> None:
        """Initialize the collector with empty bindings and module scope."""
        super().__init__()
        self.bindings: list[NameBinding] = []
        self.unresolved_variables: list[tuple[NameBinding, str]] = []
        self.scope_stack: ScopeStack = create_initial_stack()

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit a function definition and track the scope."""
        self.scope_stack = add_scope(self.scope_stack, Scope(ScopeKind.FUNCTION, node.name))
        self.generic_visit(node)
        self.scope_stack = drop_last_scope(self.scope_stack)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit an async function definition and track the scope."""
        self.scope_stack = add_scope(self.scope_stack, Scope(ScopeKind.FUNCTION, node.name))
        self.generic_visit(node)
        self.scope_stack = drop_last_scope(self.scope_stack)

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit a class definition and track the scope."""
        self.scope_stack = add_scope(self.scope_stack, Scope(ScopeKind.CLASS, node.name))
        self.generic_visit(node)
        self.scope_stack = drop_last_scope(self.scope_stack)

    @override
    def visit_Import(self, node: ast.Import) -> None:
        """Track module imports like 'import math' or 'import numpy as np'."""
        for alias in node.names:
            binding = NameBinding(
                name=alias.asname or alias.name,
                line_number=node.lineno,
                kind=NameBindingKind.IMPORT,
                qualified_name=None,  # Unresolvable in Phase 1
                scope_stack=self.scope_stack,
                source_module=alias.name,  # Track for Phase 2
                target_class=None,
            )
            self.bindings.append(binding)

    @override
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Track from imports like 'from math import sqrt' or 'from math import *'."""
        for alias in node.names:
            binding = NameBinding(
                name=alias.asname or alias.name,
                line_number=node.lineno,
                kind=NameBindingKind.IMPORT,
                qualified_name=None,  # Unresolvable in Phase 1
                scope_stack=self.scope_stack,
                source_module=node.module,  # Track for Phase 2
                target_class=None,
            )
            self.bindings.append(binding)
