# Single Collector Architecture with Position-Aware Resolution

## Overview

This plan implements a major architectural refactor to fix the import shadowing bug (issue #31) and simplify the codebase by replacing 5 separate AST visitors with a single NameBindingCollector that tracks all name bindings with their line numbers. This enables correct Python shadowing semantics through position-aware name resolution.

The new architecture:
1. **Single AST pass** (NameBindingCollector) collects all name bindings with positions
2. **PositionIndex** provides O(log k) position-aware name resolution using binary search
3. **Fixes shadowing bug** by resolving names based on their position in the file
4. **Simplifies codebase** by eliminating 5 separate visitors and their registries

## Code Reuse Inventory

### Existing utilities to leverage:
- **scope_tracker.py**:
  - `ScopeStack` type and management functions (add_scope, drop_last_scope, create_initial_stack)
  - `build_qualified_name()` for constructing qualified names from scope
  - `resolve_name_in_scope()` as reference for resolution logic
  - `extract_attribute_chain()` for handling attribute access

- **models.py**:
  - `Scope` and `ScopeKind` enums for scope tracking
  - `@dataclass(frozen=True)` pattern for immutable data
  - `QualifiedName` type for type safety

- **AST visitor patterns**:
  - Scope entry/exit patterns from existing visitors
  - visit_FunctionDef/AsyncFunctionDef/ClassDef patterns
  - Import handling patterns from ImportDiscoveryVisitor

### Components to keep:
- **FunctionDefinitionVisitor** remains separate for detailed parameter extraction
- All existing analysis logic in analyzer.py (just changes data source)

## Implementation Steps

### Step 1: Add NameBindingKind enum to models.py with comprehensive tests

Add a new enum to categorize different types of name bindings:

```python
class NameBindingKind(StrEnum):
    """Type of name binding in the AST."""
    IMPORT = "import"          # from math import sqrt
    FUNCTION = "function"       # def foo(): ...
    CLASS = "class"            # class Calculator: ...
    VARIABLE = "variable"      # calc = Calculator()
```

Tests will verify:
- Enum values are correct strings
- All binding types are covered
- String representation works correctly

### Step 2: Create NameBinding dataclass with position tracking and tests

Add the core data structure that represents a name binding at a specific position:

```python
@dataclass(frozen=True)
class NameBinding:
    """A name binding at a specific position in the code."""
    name: str                           # Local name like "sqrt", "Calculator"
    line_number: int                    # Where defined/imported (1-indexed)
    kind: NameBindingKind              # Type of binding
    qualified_name: QualifiedName | None  # None for imports (Phase 1)
    scope: QualifiedName                # Scope where binding occurs
    source_module: str | None          # For imports: "math" from "from math import sqrt"
    target_class: QualifiedName | None # For variables: class they're instances of
```

Tests will cover:
- Initialization with all field combinations
- Frozen behavior (immutability)
- Equality comparisons
- Proper handling of optional fields

### Step 3: Implement PositionIndex class with binary search and comprehensive tests

Create the position-aware index that efficiently resolves names using binary search:

```python
@dataclass(frozen=True)
class PositionIndex:
    """Efficient position-aware name resolution index."""
    # Internal structure: Dict[scope][name] -> sorted list of (line_number, binding)
    _index: dict[QualifiedName, dict[str, list[tuple[int, NameBinding]]]]

    def resolve(self, name: str, line: int, scope_stack: ScopeStack) -> NameBinding | None:
        """Resolve a name at a given position using binary search."""
        # Implementation using bisect.bisect_left for O(log k) lookup
```

Tests will verify:
- Basic resolution works correctly
- Shadowing scenarios from issue #31
- Binary search efficiency (correct binding found)
- Scope chain resolution (inner scopes checked before outer)
- Edge cases (no bindings, line before any binding, etc.)

### Step 4: Create NameBindingCollector base structure with scope tracking and tests

Implement the core visitor that will collect all name bindings:

```python
class NameBindingCollector(ast.NodeVisitor):
    """Single-pass collector of all name bindings in the AST."""

    def __init__(self):
        self.bindings: list[NameBinding] = []
        self._scope_stack: ScopeStack = create_initial_stack()

    # Scope management using existing utilities from scope_tracker.py
    def visit_FunctionDef(self, node): ...
    def visit_ClassDef(self, node): ...
```

Tests will verify:
- Proper scope tracking through nested structures
- Scope stack maintained correctly
- Base visitor functionality works

### Step 5: Add import binding collection (Import, ImportFrom) with tests for all patterns

Extend collector to track imports with source module information:

```python
def visit_Import(self, node: ast.Import) -> None:
    """Track module imports like 'import math'."""
    for alias in node.names:
        binding = NameBinding(
            name=alias.asname or alias.name,
            line_number=node.lineno,
            kind=NameBindingKind.IMPORT,
            qualified_name=None,  # Unresolvable in Phase 1
            scope=build_qualified_name(self._scope_stack),
            source_module=alias.name,  # Track for Phase 2
            target_class=None
        )
        self.bindings.append(binding)

def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
    """Track from imports like 'from math import sqrt'."""
    # Similar implementation with source_module tracking
```

Tests will cover:
- Simple imports: `import math`
- From imports: `from math import sqrt`
- Aliased imports: `import numpy as np`
- Multiple imports: `from math import sqrt, cos, sin`
- Star imports: `from math import *`
- Relative imports: `from . import utils`

### Step 6: Add function binding collection (FunctionDef, AsyncFunctionDef) with tests

Track function definitions at all scope levels:

```python
def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
    """Track function definitions."""
    qualified = build_qualified_name(self._scope_stack, node.name)
    binding = NameBinding(
        name=node.name,
        line_number=node.lineno,
        kind=NameBindingKind.FUNCTION,
        qualified_name=qualified,
        scope=build_qualified_name(self._scope_stack),
        source_module=None,
        target_class=None
    )
    self.bindings.append(binding)

    # Continue traversal with updated scope
    self._scope_stack = add_scope(self._scope_stack, Scope(ScopeKind.FUNCTION, node.name))
    self.generic_visit(node)
    self._scope_stack = drop_last_scope(self._scope_stack)
```

Tests will verify:
- Module-level functions
- Nested functions (functions inside functions)
- Class methods
- Async functions
- Functions that shadow imports

### Step 7: Add class binding collection (ClassDef) with tests for nested classes

Track class definitions including nested classes:

```python
def visit_ClassDef(self, node: ast.ClassDef) -> None:
    """Track class definitions."""
    qualified = build_qualified_name(self._scope_stack, node.name)
    binding = NameBinding(
        name=node.name,
        line_number=node.lineno,
        kind=NameBindingKind.CLASS,
        qualified_name=qualified,
        scope=build_qualified_name(self._scope_stack),
        source_module=None,
        target_class=None
    )
    self.bindings.append(binding)

    # Continue traversal with class scope
    self._scope_stack = add_scope(self._scope_stack, Scope(ScopeKind.CLASS, node.name))
    self.generic_visit(node)
    self._scope_stack = drop_last_scope(self._scope_stack)
```

Tests will cover:
- Top-level classes
- Nested classes (Inner classes)
- Classes inside functions
- Classes that shadow imports

### Step 8: Add variable binding collection (Assign, AnnAssign) with tests for instance tracking

Track variable assignments that are relevant for method resolution:

```python
def visit_Assign(self, node: ast.Assign) -> None:
    """Track assignments like calc = Calculator()."""
    if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        variable_name = node.targets[0].id

        # Check if it's a class instantiation or reference
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            # calc = Calculator() - track with target_class
            target = self._resolve_class_name(node.value.func.id)
            if target:  # Only track if it's a known class
                binding = NameBinding(
                    name=variable_name,
                    line_number=node.lineno,
                    kind=NameBindingKind.VARIABLE,
                    qualified_name=build_qualified_name(self._scope_stack, variable_name),
                    scope=build_qualified_name(self._scope_stack),
                    source_module=None,
                    target_class=target
                )
                self.bindings.append(binding)
        elif isinstance(node.value, ast.Name):
            # calc = Calculator (class reference)
            # Also track function references: process_data = json.loads
            # Will need position-aware resolution to determine what node.value.id refers to
```

Tests will verify:
- Class instantiation: `calc = Calculator()`
- Class reference: `calc = Calculator`
- Function reference: `process = sqrt`
- Variable reassignment (multiple bindings for same name)
- Annotated assignments: `calc: Calculator = Calculator()`
- Assignments we ignore: `x = 5`, `y = "string"`

### Step 9: Implement build_position_index() factory with comprehensive shadowing tests

Create the factory function that builds a PositionIndex from collected bindings:

```python
def build_position_index(bindings: list[NameBinding]) -> PositionIndex:
    """Build an efficient position-aware index from bindings."""
    index: dict[QualifiedName, dict[str, list[tuple[int, NameBinding]]]] = defaultdict(lambda: defaultdict(list))

    for binding in bindings:
        # Add to index, maintaining sorted order by line number
        index[binding.scope][binding.name].append((binding.line_number, binding))

    # Sort each name's bindings by line number for binary search
    for scope_dict in index.values():
        for binding_list in scope_dict.values():
            binding_list.sort(key=lambda x: x[0])

    return PositionIndex(_index=dict(index))
```

Tests focusing on shadowing scenarios from issue #31:
- Import shadowed by local function
- Local function shadowed by later import
- Variable reassignments
- Class shadowing import
- Multiple shadows in same scope

### Step 10: Update CallCountVisitor to use PositionIndex with shadowing scenario tests

Modify CallCountVisitor to use the new position-aware resolution:

```python
class CallCountVisitor(ast.NodeVisitor):
    def __init__(self, ..., position_index: PositionIndex, ...):
        self._position_index = position_index
        # Remove old registry dependencies

    def _resolve_direct_call(self, func: ast.Name) -> QualifiedName | None:
        """Resolve using position-aware index."""
        binding = self._position_index.resolve(
            func.id,
            func.lineno,
            self._scope_stack
        )

        if binding is None or binding.kind == NameBindingKind.IMPORT:
            return None  # Unresolvable

        if binding.kind == NameBindingKind.CLASS:
            return make_qualified_name(f"{binding.qualified_name}.__init__")

        if binding.kind == NameBindingKind.FUNCTION:
            return binding.qualified_name

        return None  # Variables aren't directly callable
```

**Note**: This commit will be larger as we need to update all CallCountVisitor tests in the same commit. Use sub-agents to help fix the tests efficiently.

Tests will verify all shadowing scenarios work correctly:
- Test cases directly from issue #31
- Complex shadowing with multiple redefinitions
- Shadowing in nested scopes

### Step 11: Integrate NameBindingCollector in analyzer.py with integration tests

Update the main analysis pipeline to use the new collector:

```python
def analyze_ast(tree: ast.Module, source_code: str, filename: str = "test.py") -> AnalysisResult:
    file_path_obj = Path(filename)

    # Single collection pass
    collector = NameBindingCollector()
    collector.visit(tree)

    # Build position-aware index
    position_index = build_position_index(collector.bindings)

    # Parse function definitions (kept separate for detailed info)
    # Note: FunctionDefinitionVisitor might need minor updates to work without ClassRegistry
    function_infos = parse_function_definitions(tree, file_path_obj, position_index)

    if not function_infos:
        return AnalysisResult(priorities=(), unresolvable_calls=())

    # Count function calls with new position-aware resolution
    resolved_counts, unresolvable_calls = count_function_calls(
        tree, function_infos, position_index, source_code
    )

    # Rest of analysis remains the same...
```

Integration tests will verify:
- End-to-end analysis works with new architecture
- Shadowing bugs from issue #31 are fixed
- Performance is acceptable
- All existing functionality preserved

### Step 12: Remove old visitors and registries with test cleanup

Clean up the codebase by removing obsolete components:

Files to delete:
- `ast_visitors/import_discovery.py` and its tests
- `ast_visitors/class_discovery.py` and its tests
- `ast_visitors/variable_discovery.py` and its tests
- `import_registry.py` and its tests
- `variable_registry.py` and its tests

Updates needed:
- Remove imports of deleted modules throughout codebase
- Update any remaining references
- Ensure all tests still pass

This step confirms the refactor is complete and the old code is no longer needed.

### Step 13: Update FunctionDefinitionVisitor to work with PositionIndex and add tests

Since FunctionDefinitionVisitor remains separate but previously depended on ClassRegistry, update it to work with PositionIndex:

```python
class FunctionDefinitionVisitor(ast.NodeVisitor):
    def __init__(self, file_path: Path, position_index: PositionIndex):
        self._position_index = position_index
        # Use position_index for any class resolution needs
```

Tests will verify:
- Function parsing still works correctly
- Class method detection works with new index
- All parameter extraction functionality preserved

## Testing Strategy

Each step includes comprehensive tests to ensure correctness:

1. **Unit tests** for each new component (NameBinding, PositionIndex, etc.)
2. **AST visitor tests** using small code snippets to verify binding collection
3. **Integration tests** ensuring the full pipeline works correctly
4. **Regression tests** for issue #31 shadowing scenarios
5. **Performance tests** confirming O(log k) lookup performance

**Important**: When updating CallCountVisitor (Step 10), we'll need to update many tests at once. Plan to use sub-agents to help with test fixes to keep the commit size manageable.

## Migration Notes

- This will be implemented on a separate branch
- Each commit should be atomic and pass all tests (100% coverage, pyright, ruff)
- Commits should be sized to fit in a single Claude context window
- No backward compatibility needed (personal project)
- The architecture is designed to extend naturally to Phase 2 (multi-file analysis)

## Success Criteria

1. **Bug fix**: Shadowing issue #31 is resolved with correct Python semantics
2. **Performance**: Reduced from 5+ AST passes to 2 (NameBindingCollector + FunctionDefinitionVisitor)
3. **Simplification**: Codebase has fewer files and clearer architecture
4. **Maintainability**: Single source of truth for name bindings
5. **Tests**: All tests pass with 100% coverage
6. **Future-ready**: Architecture prepared for Phase 2 multi-file analysis

## Assumptions and Dependencies

- Python 3.13+ with standard library bisect module
- Existing scope_tracker.py utilities work correctly
- FunctionDefinitionVisitor can be adapted to use PositionIndex
- Test updates can be done incrementally (with sub-agent help for large updates)
- Import source modules tracked for future Phase 2 use
- Variable reassignments are tracked with line numbers
- Attribute chains remain unresolvable for now (future enhancement)
