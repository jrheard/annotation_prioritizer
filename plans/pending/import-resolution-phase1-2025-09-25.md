# Import Resolution (Phase 1 - Single File) Implementation Plan

## Overview

This plan implements import resolution for single-file analysis, laying the foundation for future multi-file support. We'll track all import statements in a file, building a registry that maps imported names to their source modules while respecting Python's scope semantics.

## Goals

1. Track all import statements (module and from-imports) with their scope context
2. Distinguish between imported-but-unresolvable calls and completely unknown calls
3. Set foundation for Phase 2 multi-file analysis by tracking source module information
4. Maintain conservative resolution philosophy - only track what we're confident about

## Implementation Steps

### Phase A: Build Import Infrastructure (No Breaking Changes)

These steps can be done incrementally with full test coverage. Nothing breaks because it's all new code.

### Step 1: Add Import Data Models ✅ COMPLETED

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
- `sqrt.something()` where sqrt is a from-import

**Tests to add:**
- None, this is just a dataclass with no behavior

### Step 2: Create Import Registry ✅ COMPLETED

Add the registry structure in a new `src/annotation_prioritizer/import_registry.py`:

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
                # Import is visible if:
                # 1. Declared in exactly the current scope, OR
                # 2. Declared in a parent scope (must be followed by a dot)
                # This avoids false matches like "__module__.foo_bar" matching "__module__.foo"
                if current_scope == imp.scope or current_scope.startswith(imp.scope + "."):
                    return imp
        return None
```

**Tests to add:**
- Test lookup with various scope contexts
- Verify scope visibility rules (parent scope imports visible in child scopes)
- Test that sibling scope imports are not visible
- Test edge case: imports in `foo()` are NOT visible in `foo_bar()` (similar prefixes)

### Step 3: Implement Import Discovery Visitor ✅ COMPLETED

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

**Note**: The build_import_registry function should always be called, even for files with no imports. It should return an ImportRegistry with an empty frozenset rather than None. This ensures consistent behavior across the codebase.

### Phase B: Atomic Integration (Single Commit) ✅ COMPLETED

**CRITICAL**: Phase B must be done in a SINGLE COMMIT to avoid breaking tests. Since there are only 3 call sites for count_function_calls (analyzer.py and tests/helpers/function_parsing.py), we can update them all atomically.

### Step 4: Integrate Import Registry Everywhere ✅ COMPLETED

This step combines all integration changes into one atomic commit:

#### 4.1: Update analyzer.py

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

#### 4.2: Update Call Counter

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

#### 4.3: Update Test Helpers

Update `tests/helpers/function_parsing.py` to build and pass the import registry:

```python
def count_calls_from_file(
    file_path: Path, known_functions: tuple[FunctionInfo, ...]
) -> tuple[tuple[CallCount, ...], tuple[UnresolvableCall, ...]]:
    """Count function calls from a file with full AST and registry context."""
    parse_result = parse_ast_from_file(file_path)
    if not parse_result:
        return ((), ())

    tree, source_code = parse_result
    class_registry = build_class_registry(tree)
    variable_registry = build_variable_registry(tree, class_registry)
    import_registry = build_import_registry(tree)  # NEW

    return count_function_calls(
        tree, known_functions, class_registry, variable_registry, import_registry, source_code
    )
```

**Note**: Any other helper functions that call count_function_calls must also be updated in this commit.

#### 4.4: Integrate Import Checking in Direct Call Resolution

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

#### 4.5: Integrate Import Checking in Method Call Resolution

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

**End of Atomic Commit**

At this point, all tests should pass. The import registry is built and passed through the entire pipeline, and the resolution logic checks for imports.

### Phase C: Add Comprehensive Tests

### Step 5: Add Import-Specific Tests ✅ COMPLETED

**Note**: The implementation exceeded the planned test coverage. The actual `tests/unit/test_import_discovery.py` includes all planned tests plus additional comprehensive test cases:

- All planned tests (simple import, aliased, from-import, relative, nested, star import, scope visibility)
- Additional tests: from-import with alias, nested imports in classes, dotted module imports, async function imports, conditional imports, multiple aliases, import visibility in nested scopes, and more
- Separate `test_import_registry.py` for thorough registry lookup testing
- Total of 15+ comprehensive test functions covering all edge cases

### Step 6: Add Integration Tests

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

Add additional integration tests to verify:
- Imported functions are marked as unresolvable (not unknown)
- Module imports like math() return None
- Module methods like math.sqrt() are detected but unresolved
- Regular function calls still work normally

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

## Appendix: Phase 2 Multi-File Analysis Design

This appendix outlines how Phase 2 would build upon Phase 1's foundation to achieve full directory/project analysis.

NOTE THAT THIS IS JUST A SKETCH. We might choose to design/implement phase 2 in a different way entirely. This appendix just explains why phase 1's design is expected to be relevant to future phase 2 work.

### Phase 2 Overview

Phase 2 transforms unresolvable imports from Phase 1 into resolved function calls by analyzing multiple files together. While Phase 1 identifies and tracks imports, Phase 2 performs the actual resolution across file boundaries.

### Core Components

#### 1. Project-Wide Context Aggregation

Phase 2 would aggregate individual file analyses into a project context:

```python
@dataclass(frozen=True)
class ProjectContext:
    """Aggregates analysis data across all files in a project."""
    file_analyses: dict[Path, FileAnalysis]  # Path -> individual file's analysis
    import_graph: ImportGraph  # Tracks which files import from which

    def resolve_import(self, from_file: Path, import_name: ImportedName) -> FunctionInfo | None:
        """Resolve an import from Phase 1 to an actual function."""
        # Use import_name.source_module from Phase 1
        if import_name.source_module:
            # Absolute import like "math" or "mypackage.utils"
            target_file = self._find_module_file(import_name.source_module)
        else:
            # Relative import - use import_name.relative_level from Phase 1
            target_file = self._resolve_relative_import(
                from_file,
                import_name.relative_level,
                import_name.local_name
            )

        if target_file and target_file in self.file_analyses:
            target_analysis = self.file_analyses[target_file]
            # Look up the actual function in the target file
            return target_analysis.lookup_function(import_name.original_name or import_name.local_name)
        return None
```

#### 2. Enhanced Call Resolution

Phase 2 would extend Phase 1's resolution to handle imports:

```python
def _resolve_direct_call_phase2(self, func: ast.Name, project: ProjectContext) -> QualifiedName | None:
    """Phase 2 version that can resolve imports."""
    # First check Phase 1's import registry
    import_info = self._import_registry.lookup_import(func.id, self._scope_stack)

    if import_info:
        if import_info.is_module_import:
            # Still can't call a module directly
            return None
        else:
            # Phase 2: Actually resolve the import
            resolved_func = project.resolve_import(self._current_file, import_info)
            if resolved_func:
                return resolved_func.qualified_name
            # If we can't find it (external library), still unresolvable
            return None

    # Rest is same as Phase 1 - local resolution
    return resolve_name_in_scope(...)
```

#### 3. Module Method Resolution

Phase 2 would resolve module method calls identified by Phase 1:

```python
def _resolve_method_call_phase2(self, func: ast.Attribute, project: ProjectContext) -> QualifiedName | None:
    """Phase 2 version that can resolve module methods."""
    if isinstance(func.value, ast.Name):
        variable_name = func.value.id

        # Check Phase 1's import registry
        import_info = self._import_registry.lookup_import(variable_name, self._scope_stack)

        if import_info and import_info.is_module_import:
            # Phase 2: Resolve module.method calls
            module_file = project.find_module_file(import_info.source_module)

            if module_file:
                module_analysis = project.file_analyses[module_file]
                # Look for func.attr in the module
                target_func = module_analysis.lookup_function(func.attr)
                if target_func:
                    return target_func.qualified_name

            # External library (numpy, pandas, etc) - still unresolvable
            return None

        # Rest handles variable.method() same as Phase 1
```

### How Phase 1 Enables Phase 2

#### Source Module Tracking
Phase 1's `ImportedName.source_module` field tells Phase 2 exactly where to look for the imported item. For `import pandas as pd`, Phase 1 records `source_module="pandas"`, which Phase 2 uses to locate the pandas package in the project.

#### Relative Import Resolution
Phase 1's `ImportedName.relative_level` field enables Phase 2 to resolve relative imports correctly:

```python
def _resolve_relative_import(from_file: Path, level: int, module: str) -> Path:
    """Use Phase 1's relative_level to find the target file."""
    current_dir = from_file.parent
    for _ in range(level - 1):  # Go up 'level' directories
        current_dir = current_dir.parent
    return current_dir / module.replace('.', '/') / "__init__.py"
```

#### Scope-Aware Import Visibility
Phase 1's scope tracking ensures Phase 2 respects Python's import visibility rules. An import inside a function is only visible within that function's scope, which Phase 1's `ImportedName.scope` field preserves for Phase 2's use.

### Directory Analysis Implementation

The main entry point for Phase 2 would orchestrate multi-file analysis:

```python
def analyze_directory(directory: Path) -> ProjectAnalysisResult:
    """Phase 2's main entry point for directory analysis."""
    # Step 1: First pass - analyze each file with Phase 1 infrastructure
    file_analyses = {}
    for py_file in directory.rglob("*.py"):
        tree = ast.parse(py_file.read_text())

        # Build Phase 1 registries for this file
        import_registry = build_import_registry(tree)  # From Phase 1
        class_registry = build_class_registry(tree)
        variable_registry = build_variable_registry(tree, class_registry)

        file_analyses[py_file] = FileAnalysis(
            imports=import_registry,
            classes=class_registry,
            variables=variable_registry,
            functions=parse_function_definitions(tree, py_file, class_registry)
        )

    # Step 2: Build project context
    project = ProjectContext(file_analyses, build_import_graph(file_analyses))

    # Step 3: Second pass - resolve all calls with cross-file knowledge
    all_priorities = []
    for py_file, analysis in file_analyses.items():
        resolved_counts, unresolvable = count_function_calls_phase2(
            analysis.tree,
            analysis.functions,
            analysis.classes,
            analysis.variables,
            analysis.imports,  # Phase 1's import registry
            project  # Cross-file context
        )
        all_priorities.extend(calculate_priorities(resolved_counts, analysis.functions))

    # Step 4: Aggregate and rank across entire project
    return ProjectAnalysisResult(
        priorities=sorted(all_priorities, key=lambda p: p.priority_score, reverse=True),
        total_files=len(file_analyses),
        cross_file_calls=count_cross_file_calls(project)
    )
```

### Division of Responsibilities

**Phase 1 Provides:**
- Import identification and tracking (ImportRegistry)
- Source module information for each import
- Relative import levels for path resolution
- Scope-aware visibility rules
- Clear separation of "what's imported" from "what it resolves to"

**Phase 2 Adds:**
- Multi-file scanning and aggregation
- Import resolution to actual functions/classes
- Cross-file call counting
- Project-wide priority rankings
- Import graph construction for dependency tracking

### Implementation Benefits

This phased approach offers several advantages:

1. **Testability**: Phase 1 can be thoroughly tested in isolation by verifying imports are tracked correctly, without needing multi-file test fixtures.

2. **Incremental Progress**: Phase 1 provides immediate value by distinguishing imported-but-unresolvable calls from completely unknown calls, improving single-file analysis accuracy.

3. **Clean Separation**: Phase 1 handles the complexity of import parsing and scope tracking, allowing Phase 2 to focus purely on resolution logic.

4. **Reusability**: Phase 1's ImportRegistry can be reused for other analyses that need import information, not just call counting.

### Limitations and External Libraries

Even with Phase 2, calls to external libraries (numpy, pandas, standard library) would remain unresolvable unless we either:
1. Include those libraries in the analysis scope (potentially massive)
2. Build hardcoded knowledge of common library APIs
3. Accept that external calls remain unresolved (most pragmatic)

The pragmatic approach aligns with the project's philosophy of conservative, accurate analysis - only counting what we can confidently resolve.
