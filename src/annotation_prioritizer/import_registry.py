"""Import tracking and registry for the type annotation analyzer.

This module provides data structures and utilities for tracking import statements
in Python source files, including their scope context and resolution capabilities.
"""

from dataclasses import dataclass

from annotation_prioritizer.models import QualifiedName, make_qualified_name
from annotation_prioritizer.scope_tracker import ScopeStack


@dataclass(frozen=True)
class ImportedName:
    """Represents an imported name and its source.

    Examples:
        import math -> ImportedName("math", "math", None, True, 0, "__module__")
        from typing import List -> ImportedName("List", "typing", None, False, 0, "__module__")
        import pandas as pd -> ImportedName("pd", "pandas", None, True, 0, "__module__")
        from ..utils import helper -> ImportedName("helper", "utils", None, False, 2, "__module__")
    """

    local_name: str  # Name used in this file (e.g., "pd", "sqrt", "List")
    source_module: str | None  # Module path (e.g., "pandas", "math", "typing"), None for relative
    original_name: str | None  # Original name if aliased (e.g., "DataFrame" for "as DataFrame")
    is_module_import: bool  # Distinguishes module imports from item imports (see below)
    relative_level: int  # 0 for absolute, 1 for ".", 2 for "..", etc.
    scope: QualifiedName  # Scope where import occurs (e.g., "__module__", "__module__.func")


@dataclass(frozen=True)
class ImportRegistry:
    """Registry of imported names in the analyzed file.

    Maps imported names to their sources, respecting Python's scope rules.
    Imports are only visible in their declared scope and child scopes.
    """

    imports: frozenset[ImportedName]

    def lookup_import(self, name: str, scope_stack: ScopeStack) -> ImportedName | None:
        """Find an import by name, checking current and parent scopes.

        Args:
            name: The name to look up (e.g., "math", "List")
            scope_stack: Current scope context for resolution

        Returns:
            ImportedName if found in accessible scope, None otherwise
        """
        # Build qualified scope name from stack by joining all scope names
        current_scope = make_qualified_name(".".join(s.name for s in scope_stack))

        # Check each import to see if it's visible in current scope
        for imp in self.imports:
            # Import is visible if:
            # 1. Name matches AND
            # 2. (Declared in exactly the current scope OR in a parent scope)
            # This avoids false matches like "__module__.foo_bar" matching "__module__.foo"
            if imp.local_name == name and (
                current_scope == imp.scope or current_scope.startswith(imp.scope + ".")
            ):
                return imp
        return None
