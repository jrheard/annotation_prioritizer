# Import Resolution (Phase 1 - Single File) Implementation Plan

## Overview

This plan implements import resolution for single-file analysis, laying the foundation for future multi-file support. We'll track all import statements in a file, building a registry that maps imported names to their source modules while respecting Python's scope semantics.

## Goals

1. Track all import statements (module and from-imports) with their scope context
2. Distinguish between imported-but-unresolvable calls and completely unknown calls
3. Set foundation for Phase 2 multi-file analysis by tracking source module information
4. Maintain conservative resolution philosophy - only track what we're confident about

## Implementation Steps

### Step 1: Add Import Data Models

Create the data structures for tracking imports in `src/annotation_prioritizer/models.py`:

```python
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
```

**Why `is_module_import` matters:**
- When `True` (from `import math`): The name refers to a module object. Can only be used with dot notation like `math.sqrt()`. Direct calls like `math()` are invalid Python.
- When `False` (from `from math import sqrt`): The name refers to a specific callable/class/variable. Can be called directly like `sqrt()`, but not used with dot notation.

This distinction is critical for call resolution:
- `math()` where math is a module import → Invalid, return None
- `sqrt()` where sqrt is a from-import → Valid call (though unresolvable in Phase 1)
- `math.sqrt()` where math is a module import → Valid module method call
- `sqrt.something()` where sqrt is a from-import → Usually invalid

**Tests to add:**
- Unit tests for ImportedName creation with various import patterns
- Verify frozen dataclass behavior

### Step 2: Create Import Registry

Add the registry structure, either in `models.py` or a new `src/annotation_prioritizer/import_registry.py`:

```python
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
        # Build qualified scope name from stack
        current_scope = build_qualified_name(scope_stack[:-1], scope_stack[-1].name)

        # Check each import to see if it's visible in current scope
        for imp in self.imports:
            if imp.local_name == name:
                # Import is visible if declared in current scope or parent scope
                if current_scope.startswith(imp.scope):
                    return imp
        return None
```

**Tests to add:**
- Test lookup with various scope contexts
- Verify scope visibility rules (parent scope imports visible in child scopes)
- Test that sibling scope imports are not visible

### Step 3: Implement Import Discovery Visitor

Create `src/annotation_prioritizer/ast_visitors/import_discovery.py`:

```python
import ast
from annotation_prioritizer.models import ImportedName, QualifiedName
from annotation_prioritizer.import_registry import ImportRegistry
from annotation_prioritizer.scope_tracker import (
    ScopeStack,
    add_scope,
    build_qualified_name,
    create_initial_stack,
    drop_last_scope,
)

class ImportDiscoveryVisitor(ast.NodeVisitor):
    """Discovers all import statements in an AST with their scope context."""

    def __init__(self) -> None:
        super().__init__()
        self.imports: list[ImportedName] = []
        self._scope_stack: ScopeStack = create_initial_stack()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Track function scope for imports inside functions."""
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.FUNCTION, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Track async function scope."""
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.FUNCTION, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track class scope for imports inside classes."""
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.CLASS, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    def visit_Import(self, node: ast.Import) -> None:
        """Handle 'import X' and 'import X as Y' statements.

        Examples:
            import math
            import pandas as pd
            import xml.etree.ElementTree as ET
        """
        current_scope = build_qualified_name(self._scope_stack, "")[:-1]  # Remove trailing dot

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

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Handle 'from X import Y' statements.

        Examples:
            from typing import List, Dict
            from collections import defaultdict as dd
            from . import utils
            from ..models import User
        """
        current_scope = build_qualified_name(self._scope_stack, "")[:-1]  # Remove trailing dot

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
```

**Tests to add:**
- Test all import patterns: simple, aliased, from-imports, relative imports
- Test nested imports (in functions, classes)
- Verify star imports are skipped
- Test dotted module paths (xml.etree.ElementTree)
- Verify scope tracking is correct

### Step 4: Integrate Import Registry into Analyzer

Update `src/annotation_prioritizer/analyzer.py` to build the import registry:

```python
from annotation_prioritizer.ast_visitors.import_discovery import build_import_registry

def analyze_ast(tree: ast.Module, source_code: str, filename: str = "test.py") -> AnalysisResult:
    """Complete analysis pipeline for a parsed AST."""
    file_path_obj = Path(filename)

    # Build all registries upfront
    class_registry = build_class_registry(tree)
    variable_registry = build_variable_registry(tree, class_registry)
    import_registry = build_import_registry(tree)  # NEW

    # 1. Parse function definitions with class registry
    function_infos = parse_function_definitions(tree, file_path_obj, class_registry)

    if not function_infos:
        return AnalysisResult(priorities=(), unresolvable_calls=())

    # 2. Count function calls with all dependencies (including import registry)
    resolved_counts, unresolvable_calls = count_function_calls(
        tree, function_infos, class_registry, variable_registry, import_registry, source_code  # NEW param
    )
    # ... rest remains the same
```

**Tests to add:**
- Integration test that import registry is built and passed through pipeline
- Verify analyzer still works with the new parameter

### Step 5: Update Call Counter Constructor

Modify `src/annotation_prioritizer/ast_visitors/call_counter.py` to accept the import registry:

```python
def count_function_calls(
    tree: ast.Module,
    known_functions: tuple[FunctionInfo, ...],
    class_registry: ClassRegistry,
    variable_registry: VariableRegistry,
    import_registry: ImportRegistry,  # NEW
    source_code: str,
) -> tuple[tuple[CallCount, ...], tuple[UnresolvableCall, ...]]:
    """Count calls to known functions in the AST."""
    visitor = CallCountVisitor(
        known_functions, class_registry, source_code, variable_registry, import_registry  # NEW
    )
    visitor.visit(tree)
    # ... rest remains the same

class CallCountVisitor(ast.NodeVisitor):
    def __init__(
        self,
        known_functions: tuple[FunctionInfo, ...],
        class_registry: ClassRegistry,
        source_code: str,
        variable_registry: VariableRegistry,
        import_registry: ImportRegistry,  # NEW
    ) -> None:
        """Initialize visitor with functions to track and registries."""
        super().__init__()
        self.call_counts: dict[QualifiedName, int] = {func.qualified_name: 0 for func in known_functions}
        self._class_registry = class_registry
        self._scope_stack = create_initial_stack()
        self._source_code = source_code
        self._variable_registry = variable_registry
        self._import_registry = import_registry  # NEW
        self._unresolvable_calls: list[UnresolvableCall] = []
```

**Tests to add:**
- Update all existing call counter tests to provide import registry
- Can use empty registry for backwards compatibility

### Step 6: Integrate Import Checking in Direct Call Resolution

Update `_resolve_direct_call` in `call_counter.py`:

```python
def _resolve_direct_call(self, func: ast.Name) -> QualifiedName | None:
    """Resolve direct function calls and class instantiations."""
    # First check if it's an imported name
    import_info = self._import_registry.lookup_import(func.id, self._scope_stack)
    if import_info:
        if import_info.is_module_import:
            # It's a module import like "math" - can't be a direct call
            # math() would be calling a module, which isn't valid
            return None
        else:
            # It's an imported function/class like "sqrt" from "from math import sqrt"
            # For single-file analysis, we can't resolve to the actual function
            # Mark as unresolvable (will be handled by caller)
            return None

    # Continue with existing resolution logic
    # Try to resolve the name in the current scope
    resolved = resolve_name_in_scope(
        self._scope_stack, func.id, self._class_registry.classes | self.call_counts.keys()
    )

    if not resolved:
        return None

    # ... rest of existing logic
```

**Tests to add:**
- Test that imported functions return None (unresolvable)
- Test that module imports return None
- Test that non-imported names still resolve normally

### Step 7: Integrate Import Checking in Method Call Resolution

Update `_resolve_method_call` in `call_counter.py`:

```python
def _resolve_method_call(self, func: ast.Attribute) -> QualifiedName | None:
    """Resolve qualified name from a method call (attribute access).

    Handles self.method(), ClassName.method(), variable.method(), and
    module.function() calls.
    """
    # Check if it's a call on a variable or module
    if isinstance(func.value, ast.Name):
        variable_name = func.value.id

        # Check if it's an imported module
        import_info = self._import_registry.lookup_import(variable_name, self._scope_stack)
        if import_info and import_info.is_module_import:
            # It's a module method like math.sqrt() or pd.DataFrame()
            # For single-file analysis, mark as unresolvable
            return None

        # Continue with existing variable lookup logic
        variable_type = lookup_variable(self._variable_registry, self._scope_stack, variable_name)

        if variable_type:
            # Build the qualified method name for both instances and class refs
            return make_qualified_name(f"{variable_type.class_name}.{func.attr}")

    # ... rest of existing logic remains the same
```

**Tests to add:**
- Test that math.sqrt() is recognized as module method and returns None
- Test that pandas.DataFrame() (with alias) is recognized
- Test that regular method calls still work

### Step 8: Add Comprehensive Tests

Create `tests/unit/test_import_discovery.py`:

```python
"""Tests for import discovery and registry building."""

import ast
from annotation_prioritizer.ast_visitors.import_discovery import build_import_registry
from annotation_prioritizer.models import make_qualified_name

def test_simple_import():
    """Test basic import statement."""
    source = "import math"
    tree = ast.parse(source)
    registry = build_import_registry(tree)

    imports = list(registry.imports)
    assert len(imports) == 1
    assert imports[0].local_name == "math"
    assert imports[0].source_module == "math"
    assert imports[0].is_module_import is True

def test_aliased_import():
    """Test import with alias."""
    source = "import pandas as pd"
    tree = ast.parse(source)
    registry = build_import_registry(tree)

    imports = list(registry.imports)
    assert len(imports) == 1
    assert imports[0].local_name == "pd"
    assert imports[0].source_module == "pandas"

def test_from_import():
    """Test from-import statement."""
    source = "from typing import List, Dict"
    tree = ast.parse(source)
    registry = build_import_registry(tree)

    imports = list(registry.imports)
    assert len(imports) == 2

    names = {imp.local_name for imp in imports}
    assert names == {"List", "Dict"}

    for imp in imports:
        assert imp.source_module == "typing"
        assert imp.is_module_import is False

def test_relative_import():
    """Test relative imports."""
    source = """
from . import utils
from ..models import User
from ...lib import helper
"""
    tree = ast.parse(source)
    registry = build_import_registry(tree)

    imports = list(registry.imports)
    assert len(imports) == 3

    # Check relative levels
    utils_import = next(i for i in imports if i.local_name == "utils")
    assert utils_import.relative_level == 1
    assert utils_import.source_module is None

    user_import = next(i for i in imports if i.local_name == "User")
    assert user_import.relative_level == 2
    assert user_import.source_module == "models"

def test_nested_import_in_function():
    """Test import inside function has correct scope."""
    source = """
import math  # Module level

def my_function():
    import json  # Function level
    from typing import Optional

def another_function():
    import csv
"""
    tree = ast.parse(source)
    registry = build_import_registry(tree)

    imports = list(registry.imports)

    # Check scopes
    math_import = next(i for i in imports if i.local_name == "math")
    assert math_import.scope == make_qualified_name("__module__")

    json_import = next(i for i in imports if i.local_name == "json")
    assert json_import.scope == make_qualified_name("__module__.my_function")

    optional_import = next(i for i in imports if i.local_name == "Optional")
    assert optional_import.scope == make_qualified_name("__module__.my_function")

    csv_import = next(i for i in imports if i.local_name == "csv")
    assert csv_import.scope == make_qualified_name("__module__.another_function")

def test_star_import_ignored():
    """Test that star imports are skipped."""
    source = "from math import *"
    tree = ast.parse(source)
    registry = build_import_registry(tree)

    assert len(registry.imports) == 0  # Star import should be ignored
```

Update `tests/unit/test_unsupported.py` to verify imports are still unresolved but properly identified:

```python
def test_import_calls_remain_unresolved():
    """Test that imported function calls are still unresolved in Phase 1."""
    source = """
import math
from json import dumps
import pandas as pd

def use_imports():
    result = math.sqrt(16)  # Module method call
    data = dumps({"key": "value"})  # Direct imported function
    df = pd.DataFrame()  # Aliased module method
"""

    resolved_counts, unresolvable_calls = count_calls_from_source(source)

    # All imported calls should be unresolvable in Phase 1
    assert len(resolved_counts) == 0
    assert len(unresolvable_calls) == 3

    # But we can verify they were detected as imports (future enhancement)
    # This sets us up for Phase 2 where these will be resolvable
```

### Step 9: Update Existing Tests

Many existing tests will need the new import_registry parameter. Update helper functions:

```python
# In tests/helpers/function_parsing.py or similar
def count_calls_from_source(source: str) -> tuple[...]:
    """Helper that includes empty import registry for backwards compatibility."""
    tree = ast.parse(source)
    # ... existing setup ...
    import_registry = build_import_registry(tree)  # NEW

    resolved_counts, unresolvable_calls = count_function_calls(
        tree, function_infos, class_registry, variable_registry, import_registry, source
    )
    # ...
```

## Key Architectural Decisions

1. **Scope-Aware Imports**: Track the scope where each import occurs to match Python's semantics
2. **Conservative Resolution**: Imported calls remain unresolvable in Phase 1, but are distinguished from unknown calls
3. **Immutable Registry**: Follow existing pattern with frozen dataclasses
4. **Module-Level Building**: Build registry upfront like other registries, even for nested imports
5. **Skip Star Imports**: Too ambiguous to track reliably

## Edge Cases and Handling

1. **Import Shadowing**: VariableRegistry takes precedence (processed after imports)
   ```python
   import math
   math = "not a module"  # Variable registry will override
   ```

2. **Conditional Imports**: Track them with their actual scope
   ```python
   if TYPE_CHECKING:
       from typing import List  # Tracked at module scope
   ```

3. **Try/Except Imports**: Track all branches
   ```python
   try:
       import numpy as np
   except ImportError:
       import array as np  # Both tracked
   ```

## Success Criteria

1. All import statements are discovered and stored in ImportRegistry
2. Import scope is correctly tracked (function-level imports only visible in that function)
3. Imported function calls are marked as unresolvable (not unknown)
4. All existing tests pass with the new parameter
5. 100% test coverage maintained
6. Foundation laid for Phase 2 multi-file resolution

## Future Considerations (Phase 2)

This implementation sets up for multi-file support by:
- Tracking source_module for each import (tells us where to look)
- Tracking relative_level for relative imports (needed for path resolution)
- Keeping imports separate from resolution logic (can enhance resolution later)
- Building a registry that can be merged across files

When Phase 2 is implemented, we'll enhance the resolution logic to check if imported modules exist in the project and resolve them to actual functions.
