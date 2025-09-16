"""AST-based class discovery and registry for definitive class identification.

This module provides tools for discovering and tracking class definitions in Python
code without relying on naming heuristics. It builds a comprehensive registry of
all classes found in the AST, eliminating false positives from constants that
happen to follow naming conventions.

Key Components:
    - ClassDiscoveryVisitor: AST visitor that finds all ClassDef nodes
    - ClassRegistry: Immutable registry tracking AST classes and built-in types
    - build_class_registry: Factory function to create a registry from an AST

The class detection system supports:
    - Module-level classes
    - Nested classes (classes inside other classes)
    - Classes defined inside functions
    - Python built-in types (int, str, list, etc.)
    - Non-PEP8 class names (e.g., xmlParser, dataProcessor)
"""

import ast
import builtins
from dataclasses import dataclass
from typing import override

from annotation_prioritizer.models import Scope, ScopeKind


def _build_builtin_types() -> frozenset[str]:
    """Build a comprehensive set of Python built-in types.

    Uses the builtins module to get all built-in classes dynamically.
    This ensures we capture all built-in types including all exceptions.
    """
    return frozenset(name for name in dir(builtins) if isinstance(getattr(builtins, name), type))


PYTHON_BUILTIN_TYPES: frozenset[str] = _build_builtin_types()


@dataclass(frozen=True)
class ClassRegistry:
    """Immutable registry of known classes in the analyzed code.

    Provides definitive class identification without heuristics or guessing.
    Classes are identified from two sources:
    1. AST ClassDef nodes found during parsing
    2. Python built-in types (int, str, list, etc.)
    """

    ast_classes: frozenset[str]  # Classes found via ClassDef nodes
    builtin_classes: frozenset[str]  # Python built-in type names

    def is_class(self, name: str) -> bool:
        """Check if a name is definitively known to be a class.

        Returns True only for names we're certain are classes.
        Conservative approach: False for unknowns rather than guessing.
        """
        return name in self.ast_classes or name in self.builtin_classes

    def merge(self, other: "ClassRegistry") -> "ClassRegistry":
        """Merge with another registry (for multi-file analysis future)."""
        return ClassRegistry(
            ast_classes=self.ast_classes | other.ast_classes,
            builtin_classes=self.builtin_classes,  # Built-ins never change
        )


class ClassDiscoveryVisitor(ast.NodeVisitor):
    """Discovers all class definitions in an AST.

    Builds a registry of class names with their scope context.
    Handles nested classes correctly using the scope stack.
    """

    def __init__(self) -> None:
        """Initialize the visitor with an empty list of class names."""
        super().__init__()
        self.class_names: list[str] = []
        self._scope_stack: list[Scope] = [Scope(kind=ScopeKind.MODULE, name="__module__")]

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Record class definition with full qualified name."""
        # Build qualified name from current scope
        scope_names = [scope.name for scope in self._scope_stack]
        qualified_name = ".".join([*scope_names, node.name])
        self.class_names.append(qualified_name)

        # Push class scope and continue traversal for nested classes
        self._scope_stack.append(Scope(kind=ScopeKind.CLASS, name=node.name))
        self.generic_visit(node)
        self._scope_stack.pop()

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Track function scope for nested classes inside functions."""
        self._scope_stack.append(Scope(kind=ScopeKind.FUNCTION, name=node.name))
        self.generic_visit(node)
        self._scope_stack.pop()

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Track async function scope for nested classes."""
        self._scope_stack.append(Scope(kind=ScopeKind.FUNCTION, name=node.name))
        self.generic_visit(node)
        self._scope_stack.pop()


def build_class_registry(tree: ast.AST) -> ClassRegistry:
    """Build a complete class registry from an AST.

    Pure function that discovers all class definitions in the AST
    and combines them with Python built-in types.

    Args:
        tree: Parsed AST of Python source code

    Returns:
        Immutable ClassRegistry with all discovered classes
    """
    visitor = ClassDiscoveryVisitor()
    visitor.visit(tree)

    return ClassRegistry(
        ast_classes=frozenset(visitor.class_names),
        builtin_classes=PYTHON_BUILTIN_TYPES,
    )
