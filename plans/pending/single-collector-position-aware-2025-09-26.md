# Single Collector Architecture with Position-Aware Resolution

## Overview

This plan implements a major architectural refactor to fix the import shadowing bug (issue #31) and simplify the codebase by replacing 5 separate AST visitors with a single NameBindingCollector that tracks all name bindings with their line numbers. This enables correct Python shadowing semantics through position-aware name resolution.

The new architecture:
1. **Reduced AST passes** (NameBindingCollector) collects all name bindings with positions in a single pass
2. **PositionIndex** provides O(log k) position-aware name resolution using binary search
3. **Fixes shadowing bug** by resolving names based on their position in the file
4. **Simplifies codebase** by eliminating 5 separate visitors and their registries

## Phase Definitions

- **Phase 1 (Current State)**: Single-file analysis where imports are tracked but not resolved (we know `sqrt` was imported from `math`, but can't resolve what `math.sqrt` actually refers to). This limitation already exists in the current codebase.

- **Phase 2 (Future)**: Multi-file analysis where imports can be resolved by analyzing the imported modules. This would allow tracking calls across module boundaries. The `source_module` field in NameBinding is included now to prepare for this future enhancement.

**This plan** refactors the existing Phase 1 implementation to fix the shadowing bug and reduce AST passes by consolidating 5 separate visitors into a single NameBindingCollector.

## Out of Scope

The following Python binding scenarios are intentionally NOT supported:
- **Star imports** (`from math import *`): These are tracked as a single import binding but individual names from the star import are not resolvable
- **Regular variable assignments** (`x = 5`, `y = "string"`): Only class instantiations and class/function references are tracked. Simple assignments to literals are ignored
- Decorators (function/class decorators)
- `global` and `nonlocal` statements
- Exception handlers (`except E as e:`)
- `del` statements
- Comprehension variables (list/dict/set comprehensions have their own scope)

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

## Implementation Patterns

Several key patterns are used throughout this implementation. Understanding these upfront will help with implementing the steps below.

### Converting ScopeStack to QualifiedName

The `build_qualified_name(scope_stack, name)` function requires both a scope stack and a name to append. When you need just the scope's qualified name (without appending anything), use this pattern:

```python
# For module-level or empty scope
if not scope_stack or len(scope_stack) == 1:
    scope_name = make_qualified_name("__module__")
else:
    # Build qualified name from scope stack
    scope_name = make_qualified_name(".".join(s.name for s in scope_stack))
```

This pattern appears in multiple places:
- Building the PositionIndex (indexing by scope)
- Resolving names (looking up in each scope level)
- Converting scope contexts to qualified names

**Recommendation**: Consider extracting this as a helper function to reduce duplication:

```python
def scope_stack_to_qualified_name(scope_stack: ScopeStack) -> QualifiedName:
    """Convert a scope stack to its qualified name for indexing."""
    if not scope_stack or len(scope_stack) == 1:
        return make_qualified_name("__module__")
    return make_qualified_name(".".join(s.name for s in scope_stack))
```

### Working with Frozen Dataclasses

`NameBinding` uses `@dataclass(frozen=True)` for immutability. To update a field, create a new instance:

```python
import dataclasses

# This will raise FrozenInstanceError
# binding.target_class = new_value

# Instead, use dataclasses.replace()
updated_binding = dataclasses.replace(
    binding,
    target_class=new_value
)
```

## Implementation Steps

### Step 0: Move ScopeStack type alias from scope_tracker.py to models.py ✅

**Critical prerequisite**: This MUST be done first to avoid circular imports.

Move the line `type ScopeStack = tuple[Scope, ...]` from `scope_tracker.py` to `models.py`, placing it right after the `Scope` dataclass definition.

Then update `scope_tracker.py` to import it:
```python
from annotation_prioritizer.models import QualifiedName, Scope, ScopeKind, ScopeStack, make_qualified_name
```

**Why this is necessary**: `NameBinding` (in models.py) needs `ScopeStack` as a field type. Since `scope_tracker.py` imports from `models.py`, keeping `ScopeStack` in scope_tracker.py creates a circular dependency. This move breaks the cycle.

Tests will verify:
- All existing tests still pass (no behavior changes)
- No import errors

**Status**: ✅ Completed - ScopeStack moved to models.py:56, scope_tracker.py updated, all 260 tests pass, pyright shows no errors.

### Step 1: Add NameBindingKind enum and NameBinding dataclass to models.py ✅

Add a new enum to categorize different types of name bindings and the core data structure that represents a name binding at a specific position:

```python
class NameBindingKind(StrEnum):
    """Type of name binding in the AST."""
    IMPORT = "import"          # from math import sqrt
    FUNCTION = "function"       # def foo(): ...
    CLASS = "class"            # class Calculator: ...
    VARIABLE = "variable"      # calc = Calculator()

@dataclass(frozen=True)
class NameBinding:
    """A name binding at a specific position in the code."""
    name: str                           # Local name like "sqrt", "Calculator"
    line_number: int                    # Where defined/imported (1-indexed)
    kind: NameBindingKind              # Type of binding
    qualified_name: QualifiedName | None  # None for imports (Phase 1)
    scope_stack: ScopeStack             # Full scope stack where binding occurs
    source_module: str | None          # For imports: "math" from "from math import sqrt"
    target_class: QualifiedName | None # For variables: class they're instances of
```

**Note**: `ScopeStack` must be moved to models.py first (Step 0) for this to work.

**Status**: ✅ Completed - NameBindingKind enum and NameBinding dataclass added to models.py:59-93. All 260 tests pass with 100% coverage, pyright shows no errors.

### Step 2: Implement PositionIndex class with binary search and comprehensive tests ✅

Create the position-aware index that efficiently resolves names using binary search:

```python
@dataclass(frozen=True)
class PositionIndex:
    """Efficient position-aware name resolution index."""
    # Internal structure: Dict[scope][name] -> sorted list of (line_number, binding)
    _index: Mapping[QualifiedName, dict[str, list[tuple[int, NameBinding]]]]

    def resolve(self, name: str, line: int, scope_stack: ScopeStack) -> NameBinding | None:
        """Resolve a name at a given position using binary search."""
        # Try each scope from innermost to outermost
        # For each scope, look up bindings for this name
        # Use binary search to find the latest binding before this line

        # Binary search pattern:
        idx = bisect.bisect_left(bindings, (line, None))
        # This works because:
        # 1. bindings is a sorted list of (line_number, NameBinding) tuples
        # 2. Python compares tuples left-to-right
        # 3. We want all bindings with line_number < line
        # 4. bisect_left finds the insertion point, so idx-1 gives us the last binding before this line

        if idx > 0:
            _, binding = bindings[idx - 1]
            return binding
```

Tests will verify:
- Basic resolution works correctly
- Shadowing scenarios from issue #31
- Binary search efficiency (correct binding found)
- Scope chain resolution (inner scopes checked before outer)
- Edge cases (no bindings, line before any binding, etc.)

**Status**: ✅ Completed - PositionIndex class added to models.py:98-167 with resolve() method using binary search. Comprehensive test file created at tests/unit/test_position_index.py with 20 tests covering all scenarios including shadowing, scope chain resolution, and edge cases. All 280 tests pass with 100% coverage, pyright shows no errors.

### Step 3: Create NameBindingCollector base structure with scope tracking and tests

Implement the core visitor that will collect all name bindings:

```python
class NameBindingCollector(ast.NodeVisitor):
    """Single-pass collector of all name bindings in the AST."""

    def __init__(self):
        self.bindings: list[NameBinding] = []
        self.unresolved_variables: list[tuple[NameBinding, str]] = []  # Track variables needing resolution
        self._scope_stack: ScopeStack = create_initial_stack()

    # Scope management using existing utilities from scope_tracker.py
    def visit_FunctionDef(self, node): ...
    def visit_ClassDef(self, node): ...
```

Tests will verify:
- Proper scope tracking through nested structures
- Scope stack maintained correctly
- Base visitor functionality works

### Step 4: Add import binding collection (Import, ImportFrom) with tests for all patterns

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
            scope_stack=self._scope_stack,
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

### Step 5: Add function binding collection (FunctionDef, AsyncFunctionDef) with tests

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
        scope_stack=self._scope_stack,
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

### Step 6: Add class binding collection (ClassDef) with tests for nested classes

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
        scope_stack=self._scope_stack,
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

### Step 7: Add variable binding collection (Assign, AnnAssign) with tests for instance tracking

Track variable assignments that are relevant for method resolution. Since we can't resolve class names during collection (the index doesn't exist yet), we track unresolved references:

```python
def visit_Assign(self, node: ast.Assign) -> None:
    """Track assignments like calc = Calculator()."""
    if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        variable_name = node.targets[0].id

        # Check if it's a class instantiation or reference
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            # calc = Calculator() - track for later resolution
            class_name = node.value.func.id
            binding = NameBinding(
                name=variable_name,
                line_number=node.lineno,
                kind=NameBindingKind.VARIABLE,
                qualified_name=build_qualified_name(self._scope_stack, variable_name),
                scope_stack=self._scope_stack,
                source_module=None,
                target_class=None  # Will be resolved in build_position_index
            )
            self.bindings.append(binding)
            self.unresolved_variables.append((binding, class_name))

        elif isinstance(node.value, ast.Name):
            # calc = Calculator (class reference)
            # process = sqrt (function reference)
            # Note: function references like process = sqrt won't yet resolve if sqrt is imported
            ref_name = node.value.id
            binding = NameBinding(
                name=variable_name,
                line_number=node.lineno,
                kind=NameBindingKind.VARIABLE,
                qualified_name=build_qualified_name(self._scope_stack, variable_name),
                scope_stack=self._scope_stack,
                source_module=None,
                target_class=None  # Will be resolved in build_position_index
            )
            self.bindings.append(binding)
            self.unresolved_variables.append((binding, ref_name))
```

Tests will verify:
- Class instantiation: `calc = Calculator()`
- Class reference: `calc = Calculator`
- Function reference: `process = sqrt`
- Variable reassignment (multiple bindings for same name)
- Annotated assignments: `calc: Calculator = Calculator()`
- Assignments we ignore: `x = 5`, `y = "string"`

### Step 8: Implement build_position_index() factory with comprehensive shadowing tests

Create the factory function that builds a PositionIndex from collected bindings and resolves variable targets.

**Why two-phase resolution is necessary**: During AST traversal, we encounter variable assignments like `calc = Calculator()` where we need to resolve what `Calculator` refers to. However, we can't resolve names until we have an index to look them up in. This creates a chicken-and-egg problem:
1. We need the index to resolve class names
2. We need to resolve class names to build complete bindings
3. We need complete bindings to build the index

The solution is two phases:
- **Phase 1**: Build basic index from all bindings (with unresolved variable targets)
- **Phase 2**: Use that index to resolve variable targets, then rebuild the index with complete bindings

This approach ensures all variable targets are correctly resolved based on position-aware shadowing rules.

```python
def build_position_index(
    bindings: list[NameBinding],
    unresolved_variables: list[tuple[NameBinding, str]] | None = None
) -> PositionIndex:
    """Build an efficient position-aware index from bindings and resolve variable targets."""
    # First, build the basic index
    index: dict[QualifiedName, dict[str, list[tuple[int, NameBinding]]]] = defaultdict(lambda: defaultdict(list))

    for binding in bindings:
        # Convert scope_stack to qualified name for indexing
        # Use the scope-to-qualified-name pattern (see Implementation Patterns section)
        if not binding.scope_stack or len(binding.scope_stack) == 1:
            scope_name = make_qualified_name("__module__")
        else:
            scope_name = make_qualified_name(".".join(s.name for s in binding.scope_stack))

        index[scope_name][binding.name].append((binding.line_number, binding))

    # Sort each name's bindings by line number for binary search
    for scope_dict in index.values():
        for binding_list in scope_dict.values():
            binding_list.sort(key=lambda x: x[0])

    # If we have unresolved variables, resolve their targets and rebuild the index
    if unresolved_variables:
        import dataclasses

        # Create temporary index for resolution
        temp_index = PositionIndex(_index=dict(index))

        # Build a new list of ALL bindings with resolved variables
        # We need to iterate through all bindings to find and replace the unresolved ones
        resolved_bindings = []
        for binding in bindings:
            # Check if this binding is an unresolved variable
            is_unresolved = False
            for var_binding, target_name in unresolved_variables:
                if binding == var_binding:  # Found an unresolved variable
                    is_unresolved = True
                    # Resolve what the target refers to
                    resolved = temp_index.resolve(
                        target_name,
                        binding.line_number,
                        binding.scope_stack
                    )

                    if resolved and resolved.kind == NameBindingKind.CLASS:
                        # Create NEW binding with resolved target_class
                        # Must use dataclasses.replace() because NameBinding is frozen
                        resolved_binding = dataclasses.replace(
                            binding,
                            target_class=resolved.qualified_name
                        )
                        resolved_bindings.append(resolved_binding)
                    else:
                        # Couldn't resolve or not a class - keep original
                        resolved_bindings.append(binding)
                    break

            if not is_unresolved:
                # Not a variable - keep as-is
                resolved_bindings.append(binding)

        # Completely rebuild the index with resolved bindings
        index = defaultdict(lambda: defaultdict(list))
        for binding in resolved_bindings:
            if not binding.scope_stack or len(binding.scope_stack) == 1:
                scope_name = make_qualified_name("__module__")
            else:
                scope_name = make_qualified_name(".".join(s.name for s in binding.scope_stack))

            index[scope_name][binding.name].append((binding.line_number, binding))

        # Sort again for binary search
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

### Step 9: Update CallCountVisitor to use PositionIndex with shadowing scenario tests

Modify CallCountVisitor to use the new position-aware resolution, including support for method calls through variables.

**Registry Dependencies to Remove**:
- Remove `ImportRegistry` parameter and all import resolution logic
- Remove `ClassRegistry` parameter (replaced by `known_classes` set)
- Remove `VariableRegistry` parameter
- Remove all calls to registry methods

**New Dependencies**:
- Add `position_index: PositionIndex` parameter to `__init__`
- Add `known_classes: set[QualifiedName]` parameter (for `__init__` resolution)
- Update all resolution methods to use `position_index.resolve()`

**Signature Changes**:
```python
# Old
def __init__(self, function_infos, import_registry, class_registry, variable_registry, source_code):
    ...

# New
def __init__(self, function_infos, position_index, known_classes, source_code):
    ...
```

```python
class CallCountVisitor(ast.NodeVisitor):
    def __init__(self, ..., position_index: PositionIndex, ...):
        self._position_index = position_index
        self._known_classes: set[QualifiedName] = set()  # For __init__ resolution
        # Remove old registry dependencies

    def set_known_classes(self, classes: set[QualifiedName]) -> None:
        """Set the known classes for __init__ resolution."""
        self._known_classes = classes

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

    def _resolve_method_call(self, func: ast.Attribute) -> QualifiedName | None:
        """Resolve method calls like self.method() or ClassName.method() or calc.method()."""
        # FIRST: Handle self.method() calls (existing logic)
        if isinstance(func.value, ast.Name) and func.value.id == "self":
            # Find the containing class from scope stack
            # ... existing self resolution logic ...
            return None

        # SECOND: Handle variable.method() calls (NEW - must come before chain extraction)
        if isinstance(func.value, ast.Name):
            # Look up the variable
            binding = self._position_index.resolve(
                func.value.id,
                func.lineno,
                self._scope_stack
            )

            if binding and binding.kind == NameBindingKind.VARIABLE and binding.target_class:
                # We know what class the variable refers to
                return make_qualified_name(f"{binding.target_class}.{func.attr}")

        # THIRD: Handle ClassName.method() calls (existing logic)
        # Extract the full attribute chain and resolve
        # ... existing chain extraction logic ...
```

**Note**: This commit will be larger as we need to update all CallCountVisitor tests in the same commit. Specific tests to update:
- All tests that use ImportRegistry (remove this dependency)
- All tests that use ClassRegistry (remove this dependency)
- Add new tests for position-aware shadowing scenarios
- Ensure test coverage remains at 100%

Use sub-agents to help fix the tests efficiently.

Tests will verify all shadowing scenarios work correctly:
- Test cases directly from issue #31
- Complex shadowing with multiple redefinitions
- Shadowing in nested scopes

### Step 10: Update FunctionDefinitionVisitor to work with PositionIndex and add tests

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

**Note**: This must be done BEFORE Step 11 (integration) because analyzer.py depends on FunctionDefinitionVisitor.

### Step 11: Integrate NameBindingCollector in analyzer.py with integration tests

Update the main analysis pipeline to use the new collector:

```python
def analyze_ast(tree: ast.Module, source_code: str, filename: str = "test.py") -> AnalysisResult:
    file_path_obj = Path(filename)

    # Single collection pass
    collector = NameBindingCollector()
    collector.visit(tree)

    # Build position-aware index with resolved variable targets
    position_index = build_position_index(collector.bindings, collector.unresolved_variables)

    # Extract known classes for __init__ resolution
    # This replaces the ClassRegistry that's being removed
    known_classes = {
        binding.qualified_name
        for binding in collector.bindings
        if binding.kind == NameBindingKind.CLASS and binding.qualified_name
    }

    # Parse function definitions (kept separate for detailed info)
    # FunctionDefinitionVisitor was updated in Step 10 to use PositionIndex
    function_infos = parse_function_definitions(tree, file_path_obj, position_index)

    if not function_infos:
        return AnalysisResult(priorities=(), unresolvable_calls=())

    # Count function calls with new position-aware resolution
    # Pass known_classes to the visitor
    resolved_counts, unresolvable_calls = count_function_calls(
        tree, function_infos, position_index, known_classes, source_code
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

**Test Migration Strategy**: Before deleting test files, review them to ensure all test scenarios are covered by the new NameBindingCollector tests. Create a checklist of important test cases to verify we don't lose coverage.

This step confirms the refactor is complete and the old code is no longer needed.

## Testing Strategy

Each step includes comprehensive tests to ensure correctness:

1. **Unit tests** for each new component (NameBinding, PositionIndex, etc.)
2. **AST visitor tests** using small code snippets to verify binding collection
3. **Integration tests** ensuring the full pipeline works correctly
4. **Regression tests** for issue #31 shadowing scenarios
5. **Performance tests** confirming O(log k) lookup performance

**Important**: When updating CallCountVisitor (Step 9), we'll need to update many tests at once. Plan to use sub-agents to help with test fixes to keep the commit size manageable.

## Migration Notes

- This will be implemented on a separate branch
- Each commit should be atomic and pass all tests (100% coverage, pyright, ruff)
- Commits should be sized to fit in a single Claude context window
- No backward compatibility needed (personal project)
- The architecture is designed to extend naturally to Phase 2 (multi-file analysis)

## Success Criteria

1. **Bug fix**: Shadowing issue #31 is resolved with correct Python semantics
2. **Performance**: Reduced from 5+ AST passes to 3 (NameBindingCollector, FunctionDefinitionVisitor, CallCountVisitor)
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
