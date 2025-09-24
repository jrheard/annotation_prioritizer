# Class Instantiation Tracking Implementation Plan

## Overview

This plan implements tracking of class instantiations as calls to `__init__` methods. When code contains `Calculator()`, it will be counted as a call to `Calculator.__init__`, allowing the prioritizer to recognize that constructor methods are frequently used and should be annotated.

## Motivation

Currently, class instantiations like `Calculator()` are reported as unresolvable calls. This misses an important signal - constructors are often the most-called methods in a codebase. By tracking instantiations as `__init__` calls, we can properly prioritize constructor annotations.

## Design Decisions

### Synthetic __init__ Generation
Classes without explicit `__init__` methods will have synthetic ones generated at parse time. These synthetic methods will:
- Have a single `self` parameter with no type annotations
- Use the line number of the class definition
- Be indistinguishable from explicit `__init__` methods in the output (no special flag)

### Parameter Inference Limitations
The current implementation will NOT infer parameters from parent classes. A synthetic `__init__` always has just `(self)` as its parameter, even if the parent class has a different signature. This limitation will be addressed in future inheritance support.

### Call Counting Philosophy
We count all instantiation attempts, regardless of whether they're valid:
- `Calculator()` with missing required parameters still counts
- `Calculator(extra, params)` with too many parameters still counts
- This aligns with our role as an annotation prioritizer, not a type checker

## Implementation Steps

### Step 1: Create synthetic __init__ generation logic with tests ✅ COMPLETED

**Implementation Notes:**
- Simplified approach: Used line number 0 for all synthetic __init__ methods instead of finding actual class line numbers
- Cleaner implementation: Used list comprehension to filter classes needing synthetic __init__ before iteration
- Comprehensive test coverage: Added 8 unit tests covering various scenarios
- Fixed all integration tests to account for synthetic __init__ methods being generated

Add a new function in `src/annotation_prioritizer/ast_visitors/function_parser.py`:

```python
def generate_synthetic_init_methods(
    known_functions: tuple[FunctionInfo, ...],
    class_registry: ClassRegistry,
    tree: ast.Module,
    file_path: Path,
) -> tuple[FunctionInfo, ...]:
    """Generate synthetic __init__ methods for classes without explicit ones.

    Creates a FunctionInfo with a single 'self' parameter (no annotations) for
    each class that doesn't already have an __init__ method defined.

    Note: Does not infer parameters from parent classes. This is a limitation
    that will be addressed when inheritance support is implemented.

    Args:
        known_functions: Already discovered functions to check for existing __init__
        class_registry: Registry of all classes found in the AST
        tree: The AST module to extract class line numbers from
        file_path: Path to the source file for the FunctionInfo objects

    Returns:
        Tuple of synthetic FunctionInfo objects for missing __init__ methods
    """
```

Implementation details:
- Iterate through all classes in ClassRegistry
- Check if each class already has an __init__ in known_functions by comparing qualified names:
  ```python
  init_qualified_name = make_qualified_name(f"{class_name}.__init__")
  if any(func.qualified_name == init_qualified_name for func in known_functions):
      continue  # Skip this class, it already has __init__
  ```
- For classes without __init__, create a synthetic FunctionInfo:
  - `name = "__init__"`
  - `qualified_name = make_qualified_name(f"{class_name}.__init__")`
  - Single parameter: `ParameterInfo(name="self", has_annotation=False, is_variadic=False, is_keyword=False)`
  - `has_return_annotation = False`
  - `line_number` = line number of the ClassDef node (walk the AST to find it when needed)

Write comprehensive unit tests in `tests/unit/test_function_parser.py`:
- Class with explicit __init__ (no synthetic generated)
- Class without __init__ (synthetic generated with correct line number)
- Multiple classes, mix of with/without __init__
- Nested classes get correct qualified names
- Classes inside functions work correctly

**Commit**: `feat: add synthetic __init__ generation for classes without constructors`

### Step 2: Integrate synthetic __init__ generation into parser ✅ COMPLETED

**Implementation Notes:**
- Already implemented as part of Step 1 - the integration was done alongside the synthetic __init__ generation logic
- The parse_function_definitions function correctly calls generate_synthetic_init_methods and adds the results to the returned tuple

Modify `parse_function_definitions()` in `src/annotation_prioritizer/ast_visitors/function_parser.py`:

```python
def parse_function_definitions(
    tree: ast.Module,
    file_path: Path,
    class_registry: ClassRegistry,
) -> tuple[FunctionInfo, ...]:
    """Extract all function definitions from a parsed AST.

    Now includes synthetic __init__ methods for classes without explicit constructors.
    """
    visitor = FunctionDefinitionVisitor(file_path)
    visitor.visit(tree)

    # Generate synthetic __init__ methods for classes without them
    synthetic_inits = generate_synthetic_init_methods(
        tuple(visitor.functions),
        class_registry,
        tree,
        file_path
    )

    return tuple(visitor.functions) + synthetic_inits
```

Update integration tests to verify synthetic __init__ methods appear in parse results.

**Commit**: `feat: integrate synthetic __init__ generation into function parsing`

### Step 3: Update call resolution to handle class instantiations ✅ COMPLETED

**Implementation Notes:**
- Successfully implemented class instantiation detection for direct class names (e.g., `Calculator()`)
- Added support for nested class instantiations (e.g., `Outer.Inner()`, `Outer.Middle.Inner()`)
- Class reference assignments (e.g., `CalcClass = Calculator; CalcClass()`) are not supported - this would require value tracking

Modify `CallCountVisitor._resolve_call()` in `src/annotation_prioritizer/ast_visitors/call_counter.py`:

```python
def _resolve_call(self, func: ast.expr) -> QualifiedName | None:
    """Resolve a function call to its qualified name.

    Now also handles class instantiations by checking if the name
    refers to a known class and resolving to ClassName.__init__.
    """
    # Remove the TODO comment about class instantiation on line 254

    if isinstance(func, ast.Name):
        # Try to resolve the name in the current scope
        resolved = resolve_name_in_scope(
            self._scope_stack,
            func.id,
            self._class_registry.classes | self.call_counts.keys()
        )

        # Check if it's a known class
        if resolved and self._class_registry.is_known_class(resolved):
            # It's a class instantiation - resolve to __init__
            return make_qualified_name(f"{resolved}.__init__")

        # It's a function (or unresolvable)
        return resolved

    if isinstance(func, ast.Attribute):
        # Need to update _resolve_method_call to check if func.attr is a class
        return self._resolve_method_call(func)

    # Other node types remain unchanged
    return None
```

Also update `_resolve_method_call()` to handle class instantiations:

```python
def _resolve_method_call(self, func: ast.Attribute) -> QualifiedName | None:
    """Resolve qualified name from a method call (attribute access).

    Handles nested class instantiations like Outer.Inner() and Outer.Middle.Inner().
    """
    # ... existing self.method() and variable.method() handling ...

    # All other class method calls: extract class name and resolve
    class_name = self._extract_class_name_from_value(func.value)
    if not class_name:
        # Not a resolvable class reference (e.g., complex expression)
        return None

    # Try to resolve the class name to its qualified form
    resolved_class = self._resolve_class_name(class_name)
    if resolved_class:
        # Check if func.attr is itself a class (nested class instantiation)
        potential_nested_class = make_qualified_name(f"{resolved_class}.{func.attr}")
        if self._class_registry.is_known_class(potential_nested_class):
            # It's a nested class instantiation like Outer.Inner()
            return make_qualified_name(f"{potential_nested_class}.__init__")

        # It's a regular method call
        return make_qualified_name(f"{resolved_class}.{func.attr}")

    # Class name couldn't be resolved in any scope or registry
    return None
```

Also update `tests/integration/test_end_to_end.py` line 327 to remove the assertion that `Calculator()` is unresolvable, since it now resolves to `Calculator.__init__`.

**Commit**: `feat: detect and count class instantiations as __init__ calls`

### Step 4: Add comprehensive unit tests for class instantiation ✅ COMPLETED

**Implementation Notes:**
- Created comprehensive unit tests covering all major class instantiation scenarios
- Discovered and documented limitations during testing:
  - Loop iterations only count the instantiation once (static analysis limitation)
  - List comprehensions count as single instantiation occurrence
  - Direct instantiation method calls (Calculator().add()) are not resolved as the instance type is not tracked
- All 9 tests pass, achieving the intended goal of testing class instantiation tracking

Create new test file `tests/unit/test_class_instantiation.py`:

```python
def test_class_with_explicit_init():
    """Instantiation of class with explicit __init__ counts correctly."""
    # Test that Calculator() counts toward Calculator.__init__
    # Verify the count is accurate

def test_class_without_init():
    """Instantiation of class without __init__ counts synthetic one."""
    # Test that SimpleClass() counts toward synthetic SimpleClass.__init__

def test_multiple_instantiations():
    """Multiple instantiations are counted."""
    # Test that multiple Calculator() calls accumulate counts

def test_instantiation_with_wrong_params():
    """Instantiations with wrong parameters still count."""
    # Document that we count calls regardless of validity

def test_variable_assignment_instantiation():
    """calc = Calculator() counts as instantiation."""

def test_direct_instantiation():
    """Calculator().method() counts instantiation."""
```

Each test should verify:
- The instantiation is counted
- It's attributed to the correct __init__ method
- The count is accurate

**Commit**: `test: add unit tests for class instantiation tracking`

### Step 5: Create demo file showcasing the feature ✅ COMPLETED

**Implementation Notes:**
- Created demo file with various class instantiation patterns
- Discovered and documented that loops count as single instantiation due to static analysis limitations
- Verified output shows correct counts for WithInit, WithoutInit, and PartialAnnotations classes
- Synthetic __init__ methods are properly generated and counted

Create `demo_files/class_instantiation_demo.py`:

```python
class WithInit:
    def __init__(self, x: int) -> None:
        self.x = x

class WithoutInit:
    pass

class PartialAnnotations:
    def __init__(self, x: int, y):
        pass

# Various instantiation patterns
obj1 = WithInit(42)  # Should count toward WithInit.__init__
obj2 = WithoutInit()  # Should count toward synthetic WithoutInit.__init__
obj3 = PartialAnnotations(1, 2)  # Should count, show partial annotations

# Multiple instantiations
for i in range(5):
    WithoutInit()  # Should show count of 6 total

# Nested classes
class Outer:
    class Inner:
        pass

nested = Outer.Inner()  # Counts toward Outer.Inner.__init__
```

Manually verify the tool output shows:
- `WithInit.__init__` with count and partial annotation score
- `WithoutInit.__init__` with count (synthetic)
- Proper annotation scores for all methods

**Commit**: `docs: add demo file showing class instantiation tracking`

### Step 6: Update documentation ✅ COMPLETED

**Implementation Notes:**
- Successfully moved "Class Instantiation Tracking" from "Planned Features" section to "Current Implementation Status" section
- Added a dedicated subsection under "Analysis Capabilities" documenting the feature
- Documented all limitations including synthetic __init__ parameter inference and class reference assignments
- Clarified that all instantiation attempts are counted regardless of validity
- Updated numbering in "Planned Features" section after removing the completed feature

Update `docs/project_status.md`:
- Move "Class Instantiation Tracking" from "Planned Features" to "Current Implementation Status"
- Document the limitations regarding parameter inference
- Note that inheritance-aware parameter inference is future work
- Add note about counting all instantiation attempts regardless of validity

**Commit**: `docs: update project status for class instantiation tracking`

## Testing Strategy

Each step includes its own tests to maintain 100% coverage:
- Unit tests for pure functions (helpers, generation logic)
- Integration tests for visitor behavior
- End-to-end verification via demo files
- All tests must pass before each commit
- Pre-commit hooks (including test suite and pyright) must pass for each commit

## Rollback Plan

Each commit is atomic and can be reverted independently if issues arise. The changes are additive (new functionality) rather than modifying existing behavior, minimizing risk.

## Future Enhancements

This implementation lays groundwork for future improvements:
- **Inheritance Support**: Infer parameters from parent __init__ methods
- **Super() Tracking**: Count super().__init__() calls appropriately
- **Multiple Inheritance**: Handle MRO correctly
- **Metaclass Support**: Handle classes with custom metaclasses
- **__new__ Tracking**: Similar treatment for __new__ methods

## Success Criteria

The implementation is complete when:
1. All class instantiations are counted as __init__ calls
2. Classes without explicit __init__ have synthetic ones generated
3. 100% test coverage is maintained
4. All pre-commit hooks pass for every commit
5. Demo file clearly shows the feature working
6. Documentation is updated
