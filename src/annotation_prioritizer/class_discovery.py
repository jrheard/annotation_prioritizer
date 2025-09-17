"""AST-based class discovery and registry for definitive class identification.

This module provides tools for discovering and tracking class definitions in
Python code. It builds a comprehensive registry of all classes found in the AST.

Key Components:
    - ClassDiscoveryVisitor: AST visitor that finds all ClassDef nodes
    - ClassRegistry: Immutable registry tracking user-defined classes
    - build_class_registry: Factory function to create a registry from an AST

The class detection system supports:
    - Module-level classes
    - Nested classes (classes inside other classes)
    - Classes defined inside functions
    - Non-PEP8 class names (e.g., xmlParser, dataProcessor)
"""

import ast
from dataclasses import dataclass
from typing import override

from annotation_prioritizer.models import Scope, ScopeKind
from annotation_prioritizer.scope_tracker import ScopeStack, add_scope, create_initial_stack, drop_last_scope


@dataclass(frozen=True)
class ClassRegistry:
    """Registry of user-defined classes found in the analyzed code.

    Only tracks classes defined in the AST (via ClassDef nodes).
    Does not track Python builtins since we never analyze their methods.
    """

    classes: frozenset[str]  # Qualified names like "__module__.Calculator"

    def is_class(self, name: str) -> bool:
        """Check if a name is a known user-defined class."""
        return name in self.classes

    def merge(self, other: "ClassRegistry") -> "ClassRegistry":
        """Merge with another registry (for future multi-file analysis)."""
        return ClassRegistry(classes=self.classes | other.classes)


class ClassDiscoveryVisitor(ast.NodeVisitor):
    """Discovers all class definitions in an AST.

    Builds a registry of class names with their scope context.
    Handles nested classes correctly using the scope stack.
    """

    def __init__(self) -> None:
        """Initialize the visitor with an empty list of class names."""
        super().__init__()
        self.class_names: list[str] = []
        self._scope_stack: ScopeStack = create_initial_stack()

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Record class definition with full qualified name."""
        # Build qualified name from current scope
        scope_names = [scope.name for scope in self._scope_stack]
        qualified_name = ".".join([*scope_names, node.name])
        self.class_names.append(qualified_name)

        # Push class scope and continue traversal for nested classes
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.CLASS, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Track function scope for nested classes inside functions."""
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.FUNCTION, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Track async function scope for nested classes."""
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.FUNCTION, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)


def build_class_registry(tree: ast.AST) -> ClassRegistry:
    """Build a registry of all user-defined classes from an AST.

    Args:
        tree: Parsed AST of Python source code

    Returns:
        Immutable ClassRegistry with all discovered classes
    """
    visitor = ClassDiscoveryVisitor()
    visitor.visit(tree)

    return ClassRegistry(classes=frozenset(visitor.class_names))
