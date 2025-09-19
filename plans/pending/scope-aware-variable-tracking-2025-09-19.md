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

**IMPORTANT**: This project enforces 100% test coverage. Each commit must include both implementation AND tests (except for pure refactoring commits). All commits must pass pre-commit hooks including ruff, pyright, and pytest with 100% coverage.

### Commit 0: Extract shared name resolution utility ✅ COMPLETED

**Files to modify:**
- `src/annotation_prioritizer/scope_tracker.py` - Add public resolve_name_in_scope function
- `src/annotation_prioritizer/call_counter.py` - Update to use public function

**Implementation:**
Move `CallCountVisitor._resolve_name_in_scope()` to `scope_tracker.py` as a public function:
```python
def resolve_name_in_scope(
    scope_stack: ScopeStack,
    name: str,
    registry: Iterable[QualifiedName]
) -> QualifiedName | None:
    """Resolve a name to its qualified form by checking scope levels.

    Generates candidates from innermost to outermost scope and returns the first match.

    Args:
        scope_stack: Current scope context
        name: The name to resolve (e.g., "Calculator", "add")
        registry: Set of qualified names to check against

    Returns:
        Qualified name if found in registry, None otherwise
    """
    candidates = generate_name_candidates(scope_stack, name)
    return find_first_match(candidates, registry)
```

Update `CallCountVisitor` to use the public function:
- Replace `self._resolve_name_in_scope(name, registry)` with `resolve_name_in_scope(self._scope_stack, name, registry)`
- Remove the private `_resolve_name_in_scope` method

This refactoring enables code reuse between CallCountVisitor and VariableDiscoveryVisitor.

**Completion notes:**
- Successfully extracted `_resolve_name_in_scope` from CallCountVisitor to a public function in scope_tracker.py
- Updated both usages in CallCountVisitor to use the new public function
- Removed unused imports (generate_name_candidates, find_first_match) from call_counter.py
- All tests pass with 100% coverage maintained
- No behavior changes - pure refactoring commit

### Commit 1: Reorganize AST visitors into dedicated directory

**Files to move:**
- `src/annotation_prioritizer/call_counter.py` → `src/annotation_prioritizer/ast_visitors/call_counter.py`
- `src/annotation_prioritizer/class_discovery.py` → `src/annotation_prioritizer/ast_visitors/class_discovery.py`
- `src/annotation_prioritizer/function_parser.py` → `src/annotation_prioritizer/ast_visitors/function_parser.py`

**Files to update:**
- `src/annotation_prioritizer/__init__.py` - Update imports if needed
- `src/annotation_prioritizer/analyzer.py` - Update imports
- `src/annotation_prioritizer/cli.py` - Update imports
- All test files that import these modules

**Note**: This is a pure refactoring commit. Existing tests should continue to pass with only import path updates. No new tests needed.

### Commit 2: Add variable tracking data models and utilities with tests

**Files to create:**
- `src/annotation_prioritizer/variable_registry.py` - Data models and pure functions
- `tests/unit/test_variable_registry.py` - Unit tests for the new module

**Implementation:**
```python
"""Variable type registry and tracking utilities.

This module provides data models and utilities for tracking variable-to-type
mappings across different scopes in Python code.
"""

from collections.abc import Mapping
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
    variables: Mapping[str, VariableType]  # Immutable mapping to prevent mutation


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

**Test coverage for this commit (tests/unit/test_variable_registry.py):**
- Test `build_variable_key` with various scope depths
- Test `lookup_variable` with parent scope resolution
- Test frozen dataclass immutability
- Test edge cases (empty scope stack, non-existent variables)

### Commit 3: Create variable discovery AST visitor with comprehensive tests

**Files to create:**
- `src/annotation_prioritizer/ast_visitors/variable_discovery.py` - AST visitor for variable discovery
- `tests/unit/test_variable_discovery.py` - Comprehensive unit tests

**Implementation structure:**
```python
"""AST visitor for discovering variable-to-type mappings."""

import ast
import logging
from typing import override

from annotation_prioritizer.ast_visitors.class_discovery import ClassRegistry
from annotation_prioritizer.models import Scope, ScopeKind, make_qualified_name
from annotation_prioritizer.scope_tracker import (
    add_scope,
    create_initial_stack,
    drop_last_scope,
    resolve_name_in_scope,
    ScopeStack,
)
from annotation_prioritizer.variable_registry import (
    VariableRegistry,
    VariableType,
    build_variable_key,
)


class VariableDiscoveryVisitor(ast.NodeVisitor):
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
        self._variables: dict[str, VariableType] = {}  # Mutable dict for internal tracking

    def get_registry(self) -> VariableRegistry:
        """Return the built variable registry as an immutable registry."""
        return VariableRegistry(variables=self._variables)

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

    visit_AsyncFunctionDef = visit_FunctionDef # add pyright: ignore comment to silence pyright on this line

    @override
    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Handle annotated assignments like calc: Calculator = ..."""
        if isinstance(node.target, ast.Name):
            self._process_annotation(node.target.id, node.annotation)
        else:
            # Log when we skip complex annotated assignments
            logging.debug(
                f"Cannot track annotated assignment: complex target type "
                f"{type(node.target).__name__} not supported"
            )
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
                if class_name:
                    self._track_variable(
                        variable_name,
                        class_name,
                        is_instance=True
                    )
                else:
                    # Log when we can't resolve a call to a known class
                    logging.debug(
                        f"Cannot track assignment to '{variable_name}': "
                        f"call is not to a known class constructor"
                    )
            # Check if it's a class reference (calc = Calculator)
            elif isinstance(node.value, ast.Name):
                if self._resolve_class_name(node.value.id):
                    self._track_variable(
                        variable_name,
                        node.value.id,
                        is_instance=False
                    )
                else:
                    # Log when we encounter a name that isn't a known class
                    logging.debug(
                        f"Cannot track assignment to '{variable_name}': "
                        f"'{node.value.id}' is not a known class"
                    )
            else:
                # Log other assignment types we don't handle
                logging.debug(
                    f"Cannot track assignment to '{variable_name}': "
                    f"unsupported value type {type(node.value).__name__}"
                )
        else:
            # Log when we skip complex assignments
            if len(node.targets) > 1:
                logging.debug(
                    f"Cannot track assignment: multiple targets not supported"
                )
            elif node.targets and not isinstance(node.targets[0], ast.Name):
                logging.debug(
                    f"Cannot track assignment: complex target type "
                    f"{type(node.targets[0]).__name__} not supported"
                )

        self.generic_visit(node)

    def _process_annotation(self, variable_name: str, annotation: ast.expr) -> None:
        """Process a type annotation."""
        if isinstance(annotation, ast.Name):
            class_name = annotation.id
            if self._resolve_class_name(class_name):
                self._track_variable(variable_name, class_name, is_instance=True)
            else:
                logging.debug(
                    f"Cannot track annotation for '{variable_name}': "
                    f"'{class_name}' is not a known class"
                )
        else:
            # Log when we encounter complex annotations we don't handle
            logging.debug(
                f"Cannot track annotation for '{variable_name}': "
                f"complex annotation type {type(annotation).__name__} not supported"
            )
        # Could extend to handle Optional, Union, etc. in the future

    def _extract_class_from_call(self, call_node: ast.Call) -> str | None:
        """Extract class name from a call node if it's a known class constructor."""
        if isinstance(call_node.func, ast.Name):
            class_name = call_node.func.id
            if self._resolve_class_name(class_name):
                return class_name
        # Could handle Outer.Inner() in the future
        return None

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
            self._variables[key] = variable_type

    def _resolve_class_name(self, class_name: str) -> QualifiedName | None:
        """Resolve a class name to its qualified form."""
        return resolve_name_in_scope(
            self._scope_stack,
            class_name,
            self._class_registry.classes
        )


def build_variable_registry(tree: ast.AST, class_registry: ClassRegistry) -> VariableRegistry:
    """Build a registry of variable-to-type mappings from an AST.

    This is the entry point for the first pass of the two-pass analysis.

    Args:
        tree: Parsed AST of the Python source
        class_registry: Known classes for type validation

    Returns:
        Registry mapping scope-qualified variable names to their types
    """
    visitor = VariableDiscoveryVisitor(class_registry)
    visitor.visit(tree)
    return visitor.get_registry()
```

**Test coverage for this commit (tests/unit/test_variable_discovery.py):**
- Test direct instantiation: `calc = Calculator()`
- Test parameter annotations: `def foo(calc: Calculator)`
- Test variable annotations: `calc: Calculator = ...`
- Test reassignment tracking
- Test scope isolation (same name in different scopes)
- Test nested function parent scope access
- Test module-level variable tracking
- Test class references vs instances
- Test the `build_variable_registry` orchestration function

### Commit 4: Enhance CallCountVisitor to use VariableRegistry with tests

**Files to modify:**
- `src/annotation_prioritizer/ast_visitors/call_counter.py` - Add variable resolution
- `tests/unit/test_call_counter.py` - Add tests for variable resolution

**Implementation changes:**

1. Update imports to include variable tracking:
```python
from annotation_prioritizer.ast_visitors.variable_discovery import build_variable_registry
from annotation_prioritizer.variable_registry import lookup_variable
```

2. Update imports to include the public function:
```python
from annotation_prioritizer.scope_tracker import (
    # ... existing imports ...
    resolve_name_in_scope,
)
```

3. Modify `CallCountVisitor.__init__` to accept the registry:
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

4. Enhance `_resolve_method_call` to handle variable method calls:
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

5. Update count_function_calls to perform two-pass analysis:
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

**Test coverage for this commit (tests/unit/test_call_counter.py):**
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

### Commit 5: Add integration tests for end-to-end variable tracking

**Files to modify:**
- `tests/integration/test_end_to_end.py` - Add variable tracking scenarios

**Test the complete flow:**
- Create a file with various variable patterns
- Run the full analysis
- Verify that previously uncounted calls are now counted
- Verify that the call counts match expectations
- Ensure unresolvable calls are reduced

### Commit 6: Update project documentation

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

Each commit includes both implementation and tests to maintain 100% coverage:
- Commit 0: Extract shared utility (refactoring, existing tests should pass)
- Commit 1: Reorganize files (refactoring, update imports in existing tests)
- Commit 2: Variable registry models WITH unit tests
- Commit 3: Variable discovery visitor WITH comprehensive tests
- Commit 4: Enhanced call counter WITH tests for new functionality
- Commit 5: Integration tests for complete flow
- Commit 6: Documentation only

Run pre-commit hooks after each commit to ensure compliance:
```bash
pytest --cov=src --cov-report=term-missing --cov-fail-under=100
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
