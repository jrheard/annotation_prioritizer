"""AST visitor for discovering and tracking import statements.

This module provides tools for discovering all import statements in Python code
and building a registry that tracks their scope context and source information.
"""

import ast
from typing import override

from annotation_prioritizer.import_registry import ImportedName, ImportRegistry
from annotation_prioritizer.models import Scope, ScopeKind, make_qualified_name
from annotation_prioritizer.scope_tracker import (
    ScopeStack,
    add_scope,
    create_initial_stack,
    drop_last_scope,
)


class ImportDiscoveryVisitor(ast.NodeVisitor):
    """Discovers all import statements in an AST with their scope context."""

    def __init__(self) -> None:
        """Initialize the visitor with empty import list and module scope stack."""
        super().__init__()
        self.imports: list[ImportedName] = []
        self._scope_stack: ScopeStack = create_initial_stack()

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Track function scope for imports inside functions."""
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.FUNCTION, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Track async function scope."""
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.FUNCTION, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track class scope for imports inside classes."""
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.CLASS, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    @override
    def visit_Import(self, node: ast.Import) -> None:
        """Handle 'import X' and 'import X as Y' statements.

        Examples:
            import math
            import pandas as pd
            import xml.etree.ElementTree as ET
        """
        # Build current scope as qualified name
        current_scope = make_qualified_name(".".join(s.name for s in self._scope_stack))

        for alias in node.names:
            local_name = alias.asname if alias.asname else alias.name
            imported_name = ImportedName(
                local_name=local_name,
                source_module=alias.name,
                original_name=None,  # No specific item imported
                is_module_import=True,
                relative_level=0,
                scope=current_scope,
            )
            self.imports.append(imported_name)

        self.generic_visit(node)

    @override
    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Handle 'from X import Y' statements.

        Examples:
            from typing import List, Dict
            from collections import defaultdict as dd
            from . import utils
            from ..models import User
        """
        # Build current scope as qualified name
        current_scope = make_qualified_name(".".join(s.name for s in self._scope_stack))

        # Skip star imports - too ambiguous to track
        if any(alias.name == "*" for alias in node.names):
            return

        for alias in node.names:
            local_name = alias.asname if alias.asname else alias.name
            imported_name = ImportedName(
                local_name=local_name,
                source_module=node.module,  # Can be None for relative imports
                original_name=alias.name if alias.asname else None,
                is_module_import=False,
                relative_level=node.level,  # 0 for absolute, 1+ for relative
                scope=current_scope,
            )
            self.imports.append(imported_name)

        self.generic_visit(node)


def build_import_registry(tree: ast.Module) -> ImportRegistry:
    """Build a registry of all imports from an AST.

    Args:
        tree: Parsed AST of Python source code

    Returns:
        Immutable ImportRegistry with all discovered imports
    """
    visitor = ImportDiscoveryVisitor()
    visitor.visit(tree)

    return ImportRegistry(imports=frozenset(visitor.imports))
