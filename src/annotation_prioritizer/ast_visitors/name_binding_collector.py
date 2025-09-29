"""Single-pass collector of all name bindings in the AST.

This visitor collects all name bindings (imports, functions, classes, variables)
in a single AST traversal, tracking their positions and scope context. This enables
position-aware name resolution that correctly handles Python's shadowing semantics.
"""

import ast
from typing import override

from annotation_prioritizer.models import NameBinding, NameBindingKind, Scope, ScopeKind, ScopeStack
from annotation_prioritizer.scope_tracker import (
    add_scope,
    build_qualified_name,
    create_initial_stack,
    drop_last_scope,
)


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
        """Track function definitions and their scope."""
        # Create binding for the function name in the current scope
        qualified = build_qualified_name(self.scope_stack, node.name)
        binding = NameBinding(
            name=node.name,
            line_number=node.lineno,
            kind=NameBindingKind.FUNCTION,
            qualified_name=qualified,
            scope_stack=self.scope_stack,
            source_module=None,
            target_class=None,
        )
        self.bindings.append(binding)

        # Continue traversal with updated scope
        self.scope_stack = add_scope(self.scope_stack, Scope(ScopeKind.FUNCTION, node.name))
        self.generic_visit(node)
        self.scope_stack = drop_last_scope(self.scope_stack)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Track async function definitions and their scope."""
        # Create binding for the async function name in the current scope
        qualified = build_qualified_name(self.scope_stack, node.name)
        binding = NameBinding(
            name=node.name,
            line_number=node.lineno,
            kind=NameBindingKind.FUNCTION,
            qualified_name=qualified,
            scope_stack=self.scope_stack,
            source_module=None,
            target_class=None,
        )
        self.bindings.append(binding)

        # Continue traversal with updated scope
        self.scope_stack = add_scope(self.scope_stack, Scope(ScopeKind.FUNCTION, node.name))
        self.generic_visit(node)
        self.scope_stack = drop_last_scope(self.scope_stack)

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track class definitions and their scope."""
        # Create binding for the class name in the current scope
        qualified = build_qualified_name(self.scope_stack, node.name)
        binding = NameBinding(
            name=node.name,
            line_number=node.lineno,
            kind=NameBindingKind.CLASS,
            qualified_name=qualified,
            scope_stack=self.scope_stack,
            source_module=None,
            target_class=None,
        )
        self.bindings.append(binding)

        # Continue traversal with class scope
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

    def _track_variable_assignment(self, variable_name: str, value: ast.expr, line_number: int) -> None:
        """Track a variable assignment that may reference a class or function.

        Only tracks assignments relevant for method resolution:
        - Class instantiation: calc = Calculator()
        - Class/function references: calc = Calculator or process = sqrt

        Simple assignments to literals (x = 5, y = "string") are ignored.
        The target class/function is resolved later in build_position_index.

        Args:
            variable_name: Name of the variable being assigned to
            value: The value being assigned (right-hand side of assignment)
            line_number: Line number where the assignment occurs
        """
        # Check if it's a class instantiation or reference
        if isinstance(value, ast.Call) and isinstance(value.func, ast.Name):
            # calc = Calculator() - track for later resolution
            class_name = value.func.id
            binding = NameBinding(
                name=variable_name,
                line_number=line_number,
                kind=NameBindingKind.VARIABLE,
                qualified_name=build_qualified_name(self.scope_stack, variable_name),
                scope_stack=self.scope_stack,
                source_module=None,
                target_class=None,  # Will be resolved in build_position_index
            )
            self.bindings.append(binding)
            self.unresolved_variables.append((binding, class_name))

        elif isinstance(value, ast.Name):
            # calc = Calculator (class reference) or process = sqrt (function reference)
            ref_name = value.id
            binding = NameBinding(
                name=variable_name,
                line_number=line_number,
                kind=NameBindingKind.VARIABLE,
                qualified_name=build_qualified_name(self.scope_stack, variable_name),
                scope_stack=self.scope_stack,
                source_module=None,
                target_class=None,  # Will be resolved in build_position_index
            )
            self.bindings.append(binding)
            self.unresolved_variables.append((binding, ref_name))

    @override
    def visit_Assign(self, node: ast.Assign) -> None:
        """Track assignments like calc = Calculator() or process = sqrt.

        Only tracks assignments that are relevant for method resolution:
        - Class instantiation: calc = Calculator()
        - Class/function references: calc = Calculator or process = sqrt

        Simple assignments to literals (x = 5, y = "string") are ignored.
        The target class/function is resolved later in build_position_index.
        """
        # Only handle simple single-target assignments
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            variable_name = node.targets[0].id
            self._track_variable_assignment(variable_name, node.value, node.lineno)

    @override
    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Track annotated assignments like calc: Calculator = Calculator().

        Similar to visit_Assign, only tracks assignments relevant for method resolution.
        The annotation is ignored since we resolve the actual value.
        """
        # Only handle simple single-target assignments with a value
        if isinstance(node.target, ast.Name) and node.value is not None:
            variable_name = node.target.id
            self._track_variable_assignment(variable_name, node.value, node.lineno)
