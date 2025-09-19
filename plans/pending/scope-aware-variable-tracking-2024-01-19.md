# Scope-Aware Variable Tracking Implementation Plan

## Problem Statement

The annotation prioritizer currently cannot resolve instance method calls through variables:
```python
calc = Calculator()
calc.add(5, 7)  # Shows as 0 calls instead of 1
```

This is a critical limitation because instance method calls are extremely common in Python code. The tool can only track:
- Direct function calls: `function_name()`
- Self method calls: `self.method()`
- Static/class method calls: `ClassName.method()`

But it cannot track:
- Instance method calls via variables: `calc.add()` where `calc = Calculator()`

## Solution Overview

Implement scope-aware variable tracking using a two-pass approach:
1. **First pass**: Build a registry of variable-to-type mappings
2. **Second pass**: Use the registry to resolve method calls on variables

The solution tracks variables from three sources:
- Direct instantiation: `calc = Calculator()`
- Parameter type annotations: `def foo(calc: Calculator):`
- Variable type annotations: `calc: Calculator = get_calculator()`

## Implementation Steps

### Commit 0: Reorganize AST visitors into dedicated directory

**Files to move:**
- `src/annotation_prioritizer/call_counter.py` → `src/annotation_prioritizer/ast_visitors/call_counter.py`
- `src/annotation_prioritizer/class_discovery.py` → `src/annotation_prioritizer/ast_visitors/class_discovery.py`
- `src/annotation_prioritizer/function_parser.py` → `src/annotation_prioritizer/ast_visitors/function_parser.py`

**Files to update:**
- `src/annotation_prioritizer/__init__.py` - Update imports if needed
- `src/annotation_prioritizer/analyzer.py` - Update imports
- `src/annotation_prioritizer/cli.py` - Update imports
- All test files that import these modules

This reorganization creates a clear separation between AST traversal logic and other components.

### Commit 1: Add variable tracking data models and utilities

**Files to create:**
- `src/annotation_prioritizer/variable_registry.py` - Data models and pure functions

**Implementation:**
```python
"""Variable type registry and tracking utilities.

This module provides data models and utilities for tracking variable-to-type
mappings across different scopes in Python code.
"""

from dataclasses import dataclass

from annotation_prioritizer.models import QualifiedName
from annotation_prioritizer.scope_tracker import ScopeStack


@dataclass(frozen=True)
class VariableType:
    """Type information for a variable.

    Tracks what type a variable has been assigned or annotated with.
    The is_instance flag distinguishes between class references and instances.
    """
    class_name: QualifiedName  # e.g., "__module__.Calculator"
    is_instance: bool          # True for calc = Calculator(), False for calc = Calculator


@dataclass(frozen=True)
class VariableRegistry:
    """Registry of variable types keyed by scope-qualified names.

    Keys are formatted as:
    - Module-level: "__module__.variable_name"
    - Function-level: "__module__.function_name.variable_name"
    - Method-level: "__module__.ClassName.method_name.variable_name"
    """
    variables: dict[str, VariableType]  # Immutable after construction


def build_variable_key(scope_stack: ScopeStack, variable_name: str) -> str:
    """Build a scope-qualified key for a variable.

    Args:
        scope_stack: Current scope context
        variable_name: Local variable name

    Returns:
        Scope-qualified key like "__module__.foo.calc"
    """
    parts = [scope.name for scope in scope_stack]
    return ".".join([*parts, variable_name])


def update_variable(
    registry: VariableRegistry, key: str, variable_type: VariableType
) -> VariableRegistry:
    """Create a new registry with an updated variable mapping.

    This handles both new variables and reassignments by overwriting
    any existing entry with the same key.

    Args:
        registry: Current registry (not modified)
        key: Scope-qualified variable key
        variable_type: Type information for the variable

    Returns:
        New registry with the variable updated
    """
    new_variables = {**registry.variables, key: variable_type}
    return VariableRegistry(variables=new_variables)


def lookup_variable(
    registry: VariableRegistry,
    scope_stack: ScopeStack,
    variable_name: str
) -> VariableType | None:
    """Look up a variable's type, checking parent scopes.

    Searches from innermost to outermost scope, implementing Python's
    variable resolution rules.

    Args:
        registry: Variable registry to search
        scope_stack: Current scope context for building lookup keys
        variable_name: Variable name to look up

    Returns:
        Variable type if found in any accessible scope, None otherwise
    """
    # Try each scope level from innermost to outermost
    for i in range(len(scope_stack), 0, -1):
        partial_stack = scope_stack[:i]
        key = build_variable_key(partial_stack, variable_name)
        if key in registry.variables:
            return registry.variables[key]
    return None
```

These data models and utilities maintain functional purity and immutability throughout.

### Commit 2: Create variable discovery AST visitor

**Files to create:**
- `src/annotation_prioritizer/ast_visitors/variable_discovery.py` - AST visitor for variable discovery

**Implementation structure:**
```python
"""AST visitor for discovering variable-to-type mappings."""

import ast
from typing import override

from annotation_prioritizer.ast_visitors.class_discovery import ClassRegistry
from annotation_prioritizer.models import Scope, ScopeKind, make_qualified_name
from annotation_prioritizer.scope_tracker import (
    add_scope,
    create_initial_stack,
    drop_last_scope,
    ScopeStack,
)
from annotation_prioritizer.variable_registry import (
    VariableRegistry,
    VariableType,
    build_variable_key,
    update_variable,
)


class VariableTracker(ast.NodeVisitor):
    """AST visitor that builds a registry of variable-to-type mappings.

    First pass of the two-pass analysis. Discovers variables through:
    1. Direct instantiation: calc = Calculator()
    2. Parameter annotations: def foo(calc: Calculator)
    3. Variable annotations: calc: Calculator = ...

    Handles reassignment by tracking the most recent type.
    """

    def __init__(self, class_registry: ClassRegistry) -> None:
        """Initialize tracker with known classes.

        Args:
            class_registry: Registry of known classes for type validation
        """
        self._class_registry = class_registry
        self._scope_stack = create_initial_stack()
        self._registry = VariableRegistry(variables={})

    def get_registry(self) -> VariableRegistry:
        """Return the built variable registry."""
        return self._registry

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track class scope."""
        self._scope_stack = add_scope(
            self._scope_stack,
            Scope(kind=ScopeKind.CLASS, name=node.name)
        )
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Track function scope and parameter annotations."""
        self._scope_stack = add_scope(
            self._scope_stack,
            Scope(kind=ScopeKind.FUNCTION, name=node.name)
        )

        # Process parameter annotations
        for arg in node.args.args:
            if arg.annotation:
                self._process_annotation(arg.arg, arg.annotation)

        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Track async function scope and parameter annotations."""
        # Similar to visit_FunctionDef
        self._scope_stack = add_scope(
            self._scope_stack,
            Scope(kind=ScopeKind.FUNCTION, name=node.name)
        )

        for arg in node.args.args:
            if arg.annotation:
                self._process_annotation(arg.arg, arg.annotation)

        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    @override
    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Handle annotated assignments like calc: Calculator = ..."""
        if isinstance(node.target, ast.Name):
            self._process_annotation(node.target.id, node.annotation)
        self.generic_visit(node)

    @override
    def visit_Assign(self, node: ast.Assign) -> None:
        """Handle assignments like calc = Calculator()."""
        # Only handle simple assignments to single names
        if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            variable_name = node.targets[0].id

            # Check if it's a direct instantiation
            if isinstance(node.value, ast.Call):
                class_name = self._extract_class_from_call(node.value)
                if class_name and self._is_known_class(class_name):
                    self._track_variable(
                        variable_name,
                        class_name,
                        is_instance=True
                    )
            # Check if it's a class reference (calc = Calculator)
            elif isinstance(node.value, ast.Name):
                if self._is_known_class(node.value.id):
                    self._track_variable(
                        variable_name,
                        node.value.id,
                        is_instance=False
                    )

        self.generic_visit(node)

    def _process_annotation(self, variable_name: str, annotation: ast.expr) -> None:
        """Process a type annotation."""
        if isinstance(annotation, ast.Name):
            class_name = annotation.id
            if self._is_known_class(class_name):
                # Annotations typically indicate instances
                self._track_variable(variable_name, class_name, is_instance=True)
        # Could extend to handle Optional, Union, etc. in the future

    def _extract_class_from_call(self, call_node: ast.Call) -> str | None:
        """Extract class name from a call node if it's a constructor."""
        if isinstance(call_node.func, ast.Name):
            return call_node.func.id
        # Could handle Outer.Inner() in the future
        return None

    def _is_known_class(self, class_name: str) -> bool:
        """Check if a class name exists in the registry."""
        # Build candidates from current scope and check registry
        # Implementation would use similar logic to CallCountVisitor._resolve_class_name
        # For MVP, we'll check simple names against the registry
        for qualified in self._class_registry.classes:
            if qualified.endswith(f".{class_name}"):
                return True
        return False

    def _track_variable(
        self,
        variable_name: str,
        class_name: str,
        is_instance: bool
    ) -> None:
        """Add or update a variable in the registry."""
        key = build_variable_key(self._scope_stack, variable_name)
        # Resolve class name to qualified form
        qualified_class = self._resolve_class_name(class_name)
        if qualified_class:
            variable_type = VariableType(
                class_name=qualified_class,
                is_instance=is_instance
            )
            self._registry = update_variable(self._registry, key, variable_type)

    def _resolve_class_name(self, class_name: str) -> QualifiedName | None:
        """Resolve a class name to its qualified form."""
        # Similar logic to CallCountVisitor._resolve_class_name
        # Would reuse the name resolution utilities
        for qualified in self._class_registry.classes:
            if qualified.endswith(f".{class_name}"):
                return qualified
        return None
```

### Commit 3: Add build_variable_registry orchestration function

**Files to modify:**
- `src/annotation_prioritizer/ast_visitors/variable_discovery.py` - Add orchestration function

**Add to the end of the file:**
```python
def build_variable_registry(tree: ast.AST, class_registry: ClassRegistry) -> VariableRegistry:
    """Build a registry of variable-to-type mappings from an AST.

    This is the entry point for the first pass of the two-pass analysis.

    Args:
        tree: Parsed AST of the Python source
        class_registry: Known classes for type validation

    Returns:
        Registry mapping scope-qualified variable names to their types
    """
    tracker = VariableTracker(class_registry)
    tracker.visit(tree)
    return tracker.get_registry()
```

### Commit 4: Enhance CallCountVisitor to use VariableRegistry

**Files to modify:**
- `src/annotation_prioritizer/ast_visitors/call_counter.py` - Add variable resolution

**Changes to make:**

1. Update imports to include variable tracking:
```python
from annotation_prioritizer.ast_visitors.variable_discovery import build_variable_registry
from annotation_prioritizer.variable_registry import lookup_variable
```

2. Modify `CallCountVisitor.__init__` to accept the registry:
```python
def __init__(
    self,
    known_functions: tuple[FunctionInfo, ...],
    class_registry: ClassRegistry,
    source_code: str,
    variable_registry: VariableRegistry,  # NEW
) -> None:
    """Initialize visitor with functions to track and registries.

    Args:
        known_functions: Functions to count calls for
        class_registry: Registry of known classes
        source_code: Source code for extracting unresolvable call text
        variable_registry: Registry of variable types for resolution
    """
    # ... existing initialization ...
    self._variable_registry = variable_registry
```

3. Enhance `_resolve_method_call` to handle variable method calls:
```python
def _resolve_method_call(self, func: ast.Attribute) -> QualifiedName | None:
    """Resolve qualified name from a method call (attribute access).

    Handles self.method(), ClassName.method(), and variable.method() calls.
    """
    # ... existing self/cls handling ...

    # Check if it's a call on a variable (calc.add())
    if isinstance(func.value, ast.Name):
        variable_name = func.value.id

        # Skip self/cls (already handled above)
        if variable_name not in ("self", "cls"):
            # Look up the variable's type
            variable_type = lookup_variable(
                self._variable_registry,
                self._scope_stack,
                variable_name
            )

            if variable_type and variable_type.is_instance:
                # Build the qualified method name
                return make_qualified_name(f"{variable_type.class_name}.{func.attr}")

    # ... rest of existing logic for class method calls ...
```

### Commit 5: Update count_function_calls to perform two-pass analysis

**Files to modify:**
- `src/annotation_prioritizer/ast_visitors/call_counter.py` - Implement two-pass approach

**Update the main function:**
```python
def count_function_calls(
    file_path: str, known_functions: tuple[FunctionInfo, ...]
) -> tuple[tuple[CallCount, ...], tuple[UnresolvableCall, ...]]:
    """Count calls to known functions using two-pass analysis.

    First pass: Build variable registry for type discovery
    Second pass: Count function calls using type information
    """
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        return ((), ())

    try:
        source_code = file_path_obj.read_text(encoding="utf-8")
        tree = ast.parse(source_code, filename=file_path)
    except (OSError, SyntaxError):
        return ((), ())

    # First pass: Build registries
    class_registry = build_class_registry(tree)
    variable_registry = build_variable_registry(tree, class_registry)

    # Second pass: Count calls with type information
    visitor = CallCountVisitor(
        known_functions,
        class_registry,
        source_code,
        variable_registry  # Pass the registry
    )
    visitor.visit(tree)

    resolved = tuple(
        CallCount(function_qualified_name=name, call_count=count)
        for name, count in visitor.call_counts.items()
    )

    return (resolved, visitor.get_unresolvable_calls())
```

### Commit 6: Add comprehensive unit tests for variable tracking

**Files to create:**
- `tests/unit/test_variable_registry.py` - Test data models and utility functions
- `tests/unit/test_variable_discovery.py` - Test the tracker visitor

**Test coverage needed:**

For `test_variable_registry.py`:
- Test `build_variable_key` with various scope depths
- Test `update_variable` for both new and reassignment
- Test `lookup_variable` with parent scope resolution

For `test_variable_discovery.py`:
- Test direct instantiation: `calc = Calculator()`
- Test parameter annotations: `def foo(calc: Calculator)`
- Test variable annotations: `calc: Calculator = ...`
- Test reassignment tracking
- Test scope isolation (same name in different scopes)
- Test nested function parent scope access
- Test module-level variable tracking
- Test class references vs instances

### Commit 7: Add unit tests for enhanced CallCountVisitor

**Files to modify:**
- `tests/unit/test_call_counter.py` - Add variable resolution tests

**New test cases:**
```python
def test_count_instance_method_calls_via_variables() -> None:
    """Test that instance method calls through variables are counted."""
    code = """
class Calculator:
    def add(self, a, b):
        return a + b

def use_calculator():
    calc = Calculator()
    return calc.add(5, 6)  # Should now be counted!
"""
    # Assert calc.add() is counted once


def test_variable_reassignment_uses_latest_type() -> None:
    """Test that reassigned variables use their most recent type."""
    code = """
class Calculator:
    def add(self, a, b):
        return a + b

class Helper:
    def add(self, x, y):
        return x + y

def test():
    obj = Calculator()
    obj.add(1, 2)  # Should count as Calculator.add
    obj = Helper()
    obj.add(3, 4)  # Should count as Helper.add
"""
    # Assert correct attribution after reassignment


def test_parameter_type_annotations_enable_resolution() -> None:
    """Test that parameter type annotations enable method resolution."""
    code = """
class Calculator:
    def add(self, a, b):
        return a + b

def process(calc: Calculator):
    return calc.add(10, 20)
"""
    # Assert calc.add() is counted


def test_parent_scope_variable_access() -> None:
    """Test that nested functions can access parent scope variables."""
    code = """
class Calculator:
    def add(self, a, b):
        return a + b

def outer():
    calc = Calculator()

    def inner():
        return calc.add(1, 2)  # Should be counted

    return inner()
"""
    # Assert inner function's use of calc.add() is counted
```

### Commit 8: Add integration tests for end-to-end variable tracking

**Files to modify:**
- `tests/integration/test_end_to_end.py` - Add variable tracking scenarios

**Test the complete flow:**
- Create a file with various variable patterns
- Run the full analysis
- Verify that previously uncounted calls are now counted
- Verify that the call counts match expectations
- Ensure unresolvable calls are reduced

### Commit 9: Update project documentation

**Files to modify:**
- `docs/project_status.md` - Mark variable tracking as complete
- `src/annotation_prioritizer/ast_visitors/call_counter.py` - Update module docstring

**Update call_counter.py docstring:**
Remove the TODO comment and update the "Limitations" section to reflect that basic instance method calls via variables are now supported.

**Update project_status.md:**
Move "Instance method calls via variables" from "Not Implemented" to "Implemented" with a note about what patterns are still deferred.

## Explicitly Deferred Features

These patterns are intentionally left for future iterations:

1. **Method chaining from function returns**:
   ```python
   get_calculator().add(1, 2)  # Can't track return types yet
   ```

2. **Indexing operations**:
   ```python
   calculators = [Calculator()]
   calculators[0].add(1, 2)  # Can't track collection contents
   ```

3. **Attribute access chains**:
   ```python
   self.calc.add(1, 2)  # Can't track object attributes
   obj.nested.deeply.method()  # Complex chains
   ```

4. **Collection type annotations**:
   ```python
   calculators: list[Calculator] = []  # Generic types not handled
   ```

5. **Import tracking**:
   ```python
   from module import Calculator
   calc = Calculator()  # Cross-module types not supported
   ```

These limitations are acceptable for an MVP. The infrastructure built here provides a solid foundation for adding these features later.

## Testing Strategy

Each commit should include its associated tests to ensure atomic, working commits:
- Commit 0: Update all imports and ensure tests pass
- Commit 1: Basic model and utility function tests
- Commit 2-3: Variable discovery tests
- Commits 4-5: Enhanced call counter tests
- Commits 6-8: Comprehensive test coverage
- Commit 9: Documentation only

Run the test suite after each commit to ensure nothing breaks:
```bash
pytest
ruff check --fix
ruff format
pyright
```

## Success Criteria

The implementation is successful when:
1. `calc = Calculator(); calc.add()` is counted correctly
2. Parameter type annotations enable resolution
3. Parent scope variables are accessible to nested functions
4. Variable reassignment tracks the latest type
5. Module-level variables are tracked
6. All existing tests continue to pass
7. Test coverage remains at 100%
