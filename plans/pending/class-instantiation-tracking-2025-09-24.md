# Class Instantiation Tracking Implementation Plan

## Overview

This plan implements tracking of class instantiations as calls to `__init__` methods. When code contains `Calculator()`, it will be counted as a call to `Calculator.__init__`, allowing the prioritizer to recognize that constructor methods are frequently used and should be annotated.

## Design Decisions

### Synthetic __init__ Generation
Classes without explicit `__init__` methods will have synthetic ones generated at parse time. These synthetic methods will have a single `self` parameter with no type annotations. This ensures every class has a countable `__init__` method.

### Parameter Inference Limitations
**Important**: The current implementation will NOT infer parameters from parent classes. A synthetic `__init__` always has just `(self)` as its parameter, even if the parent class has a different signature. This means:
- `Child(42, "hello")` counts as a call to `Child.__init__`
- Our synthetic `Child.__init__` only has `(self)` parameter
- This parameter mismatch is intentional - we count calls, not validate them
- This limitation will be addressed in future inheritance support

### Call Counting Philosophy
We count all instantiation attempts, regardless of whether they're valid:
- `Calculator()` with missing required parameters still counts
- `Calculator(extra, params)` with too many parameters still counts
- This aligns with our role as an annotation prioritizer, not a type checker

### Inheritance Handling (Future Work)
For now, `SubClass()` counts only toward `SubClass.__init__()`, not parent class constructors. When we implement full inheritance support later, we'll need to:
- Track Method Resolution Order (MRO)
- Infer parameters from parent __init__ methods
- Handle super().__init__() calls properly
- Potentially count toward multiple __init__ methods in the inheritance chain

## Implementation Steps

### Step 1: Add helper function for __init__ identification

Create a helper function in `src/annotation_prioritizer/models.py` to identify __init__ methods:

```python
def is_init_method(function_info: FunctionInfo) -> bool:
    """Check if a FunctionInfo represents an __init__ method."""
    return function_info.name == "__init__"
```

Write unit tests in `tests/unit/test_models.py` to verify this helper works correctly for:
- Regular __init__ methods
- Methods with other names
- Module-level functions named __init__ (edge case)

**Commit**: "feat: add helper to identify __init__ methods"

### Step 2: Create synthetic __init__ generation logic

Add a new function in `src/annotation_prioritizer/ast_visitors/function_parser.py`:

```python
def generate_synthetic_init_methods(
    known_functions: tuple[FunctionInfo, ...],
    class_registry: ClassRegistry,
    file_path: str,
) -> tuple[FunctionInfo, ...]:
    """Generate synthetic __init__ methods for classes without explicit ones.

    Creates a FunctionInfo with a single 'self' parameter (no annotations) for
    each class that doesn't already have an __init__ method defined.

    Note: Does not infer parameters from parent classes. This is a limitation
    that will be addressed when inheritance support is implemented.

    Args:
        known_functions: Already discovered functions to check for existing __init__
        class_registry: Registry of all classes found in the AST
        file_path: Path to the source file for the FunctionInfo objects

    Returns:
        Tuple of synthetic FunctionInfo objects for missing __init__ methods
    """
```

Implementation details:
- Iterate through all classes in ClassRegistry
- Check if each class already has an __init__ in known_functions
- For classes without __init__, create a synthetic FunctionInfo:
  - `name = "__init__"`
  - `qualified_name = make_qualified_name(f"{class_name}.__init__")`
  - Single parameter: `ParameterInfo(name="self", has_annotation=False, is_variadic=False, is_keyword=False)`
  - `has_return_annotation = False`
  - `line_number = 0` (or extract from ClassDef if available)

Write comprehensive unit tests in `tests/unit/test_function_parser.py`:
- Class with explicit __init__ (no synthetic generated)
- Class without __init__ (synthetic generated)
- Multiple classes, mix of with/without __init__
- Nested classes
- Classes inside functions

**Commit**: "feat: add synthetic __init__ generation for classes without constructors"

### Step 3: Integrate synthetic __init__ generation into parser

Modify `parse_function_definitions()` in `src/annotation_prioritizer/ast_visitors/function_parser.py`:

```python
def parse_function_definitions(file_path: str) -> tuple[FunctionInfo, ...]:
    # ... existing parsing logic ...

    # After normal parsing, generate synthetic __init__ methods
    class_registry = build_class_registry(tree)
    synthetic_inits = generate_synthetic_init_methods(
        tuple(visitor.functions),
        class_registry,
        file_path
    )

    return tuple(visitor.functions) + synthetic_inits
```

Note: This requires importing `build_class_registry` from `class_discovery.py`.

Update integration tests to verify synthetic __init__ methods appear in parse results.

**Commit**: "feat: integrate synthetic __init__ generation into function parsing"

### Step 4: Add class instantiation detection helper

Add a helper function in `src/annotation_prioritizer/ast_visitors/call_counter.py`:

```python
def is_class_instantiation(
    name: str,
    class_registry: ClassRegistry,
    scope_stack: ScopeStack
) -> QualifiedName | None:
    """Check if a name refers to a class instantiation.

    Args:
        name: The name being called (e.g., "Calculator")
        class_registry: Registry of known classes
        scope_stack: Current scope context for resolution

    Returns:
        Qualified name of the class if it's a known class, None otherwise
    """
```

This helper will:
- Try to resolve the name in the current scope
- Check if the resolved name exists in the ClassRegistry
- Return the qualified class name if found

Write unit tests for various scenarios:
- Direct class name in same scope
- Class name from outer scope
- Non-class name (should return None)
- Ambiguous names

**Commit**: "feat: add helper to detect class instantiations"

### Step 5: Update call resolution to handle class instantiations

Modify `CallCountVisitor._resolve_function_call()` in `src/annotation_prioritizer/ast_visitors/call_counter.py`:

```python
def _resolve_function_call(self, function_name: str) -> QualifiedName | None:
    """Resolve a function call to its qualified name.

    Now also handles class instantiations by checking if the name
    refers to a known class and resolving to ClassName.__init__.
    """
    # First check if this is a class instantiation
    class_name = is_class_instantiation(
        function_name,
        self._class_registry,
        self._scope_stack
    )
    if class_name:
        # It's a class instantiation - resolve to __init__
        return make_qualified_name(f"{class_name}.__init__")

    # Not a class - try normal function resolution
    return resolve_name_in_scope(
        self._scope_stack,
        function_name,
        self.call_counts.keys()
    )
```

Remove or update the TODO comment on line 254 since we're now addressing it.

**Commit**: "feat: detect and count class instantiations as __init__ calls"

### Step 6: Add comprehensive integration tests

Create new test file `tests/integration/test_class_instantiation.py` with scenarios:

```python
def test_class_with_explicit_init():
    """Instantiation of class with explicit __init__ counts correctly."""

def test_class_without_init():
    """Instantiation of class without __init__ counts synthetic one."""

def test_multiple_instantiations():
    """Multiple instantiations are counted."""

def test_nested_class_instantiation():
    """Nested class instantiations work correctly."""

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

**Commit**: "test: add integration tests for class instantiation tracking"

### Step 7: Update existing tests that expect instantiations to be unresolvable

Search for existing tests that check for unresolvable calls like `Calculator()` and update them:

```bash
grep -r "Calculator()" tests/
```

These tests will now expect:
- `Calculator()` to be resolved (not unresolvable)
- Count attributed to `Calculator.__init__`

Update test expectations accordingly.

**Commit**: "test: update existing tests for class instantiation resolution"

### Step 8: Add end-to-end demonstration

Create or update a demo file to showcase the feature:

`demo_files/class_instantiation_demo.py`:
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
```

Run the tool on this file and verify output shows:
- `WithInit.__init__` with count
- `WithoutInit.__init__` with count (synthetic)
- Proper annotation scores

**Commit**: "docs: add demo file showing class instantiation tracking"

### Step 9: Update documentation

Update `docs/project_status.md`:
- Move "Class Instantiation Tracking" from "Planned Features" to "Current Implementation Status"
- Document the limitations regarding parameter inference
- Note that inheritance-aware parameter inference is future work
- Add note about counting all instantiation attempts regardless of validity

**Commit**: "docs: update project status for class instantiation tracking"

## Testing Strategy

Each step includes its own tests to maintain 100% coverage:
- Unit tests for pure functions (helpers, generation logic)
- Integration tests for visitor behavior
- End-to-end tests via demo files
- All tests must pass before committing

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
4. All pre-commit hooks pass
5. Demo file clearly shows the feature working
6. Documentation is updated
