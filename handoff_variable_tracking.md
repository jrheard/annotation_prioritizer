# Handoff: Implement Variable Tracking in Single Collector Prototype

## Your Mission
Add variable tracking to the existing prototype of the single collector architecture on the `experiment` branch. This will fix the current regression where method calls through variables (like `calc.compute()`) are not resolved.

## Current State

### What's Been Built
We have a working prototype that fixes the shadowing bug (issue #31) using position-aware name resolution. The prototype includes:

1. **NameBindingCollector** (`src/annotation_prioritizer/name_binding_collector.py`)
   - Single-pass AST visitor that collects imports, functions, and classes
   - Currently DOES NOT track variables (this is what you need to add)

2. **PositionIndex** (`src/annotation_prioritizer/position_index.py`)
   - Binary search-based name resolution that correctly handles shadowing
   - Works well for the bindings it has, just missing variable bindings

3. **CallCountVisitorPrototype** (`src/annotation_prioritizer/call_counter_prototype.py`)
   - Uses PositionIndex for resolution
   - Currently can't resolve `calc.compute()` because variables aren't tracked

4. **analyze_ast_prototype()** (`src/annotation_prioritizer/analyzer.py`)
   - Parallel implementation for testing against the original

### Test Files
- `test_shadowing_prototype.py` - Demonstrates shadowing scenarios
- `test_prototype.py` - Compares old vs new implementation

### Current Test Results
```
✓ Fixed: Lines 18, 28, 35, 40 (shadowing now works correctly)
✗ Regression: Line 48 (calc.compute() no longer resolves)
```

## Key Documents to Read

1. **MUST READ: `prototype_findings.md`**
   - Section 5 explains why variable tracking is critical
   - Shows the regression it causes when missing
   - Has specific examples of what breaks

2. **Reference: `plans/pending/single-collector-position-aware-2025-09-26.md`**
   - Step 7 describes variable tracking (but underestimates its importance)
   - Shows the unresolved_variables pattern you'll need to implement

3. **Study: `src/annotation_prioritizer/ast_visitors/variable_discovery.py`**
   - Current implementation that tracks variables
   - You'll adapt this logic into NameBindingCollector

4. **Study: `src/annotation_prioritizer/variable_registry.py`**
   - Shows how variables are currently resolved to their types
   - Important for understanding the use cases

## Implementation Plan

### Step 1: Extend NameBindingCollector

Add variable tracking to `name_binding_collector.py`:

```python
def __init__(self) -> None:
    self.bindings: list[NameBinding] = []
    self.unresolved_variables: list[tuple[NameBinding, str]] = []  # ADD THIS
    self._scope_stack: ScopeStack = create_initial_stack()

def visit_Assign(self, node: ast.Assign) -> None:
    """Track assignments like calc = Calculator()."""
    if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        variable_name = node.targets[0].id

        # Check if it's a class instantiation
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            class_name = node.value.func.id
            binding = NameBinding(
                name=variable_name,
                line_number=node.lineno,
                kind=NameBindingKind.VARIABLE,  # You'll need to add this to the enum
                qualified_name=build_qualified_name(self._scope_stack, variable_name),
                scope_stack=self._scope_stack,
                source_module=None,
                target_class=None  # Will be resolved later
            )
            self.bindings.append(binding)
            self.unresolved_variables.append((binding, class_name))

        elif isinstance(node.value, ast.Name):
            # Handle calc = Calculator (without parens)
            ref_name = node.value.id
            # Similar logic...
```

### Step 2: Add VARIABLE to NameBindingKind

In `models.py`, update the enum:
```python
class NameBindingKind(StrEnum):
    IMPORT = "import"
    FUNCTION = "function"
    CLASS = "class"
    VARIABLE = "variable"  # ADD THIS
```

### Step 3: Update build_position_index

The tricky part! After building the index, resolve variable targets:

```python
def build_position_index(
    bindings: list[NameBinding],
    unresolved_variables: list[tuple[NameBinding, str]]
) -> PositionIndex:
    # First build the basic index (existing code)
    ...

    # Create temporary index for resolution
    temp_index = PositionIndex(_index=dict(index))

    # Resolve variable targets
    resolved_bindings = []
    for binding in bindings:
        if any(binding == var_binding for var_binding, _ in unresolved_variables):
            # Find the unresolved variable entry
            for var_binding, target_name in unresolved_variables:
                if var_binding == binding:
                    # Resolve what the target refers to
                    resolved = temp_index.resolve(
                        target_name,
                        binding.line_number,
                        binding.scope_stack
                    )

                    if resolved and resolved.kind == NameBindingKind.CLASS:
                        # Create new binding with resolved target_class
                        # Note: NameBinding is frozen, so use dataclasses.replace
                        import dataclasses
                        resolved_binding = dataclasses.replace(
                            binding,
                            target_class=resolved.qualified_name
                        )
                        resolved_bindings.append(resolved_binding)
                    else:
                        resolved_bindings.append(binding)
                    break
        else:
            resolved_bindings.append(binding)

    # Rebuild index with resolved bindings
    # ... rebuild the index structure with resolved_bindings
```

### Step 4: Update NameBinding dataclass

The `target_class` field already exists but needs to be properly used:
```python
@dataclass(frozen=True)
class NameBinding:
    name: str
    line_number: int
    kind: NameBindingKind
    qualified_name: QualifiedName | None
    scope_stack: "ScopeStack"
    source_module: str | None
    target_class: QualifiedName | None  # For VARIABLE kind: the class it refers to
```

### Step 5: Update CallCountVisitorPrototype

In `_resolve_method_call`, add variable resolution:

```python
def _resolve_method_call(self, func: ast.Attribute) -> QualifiedName | None:
    # Existing self.method() handling...

    # Add variable.method() handling
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

    # Rest of existing code...
```

### Step 6: Update analyze_ast_prototype

Update the call to build_position_index:
```python
# Build position-aware index with variable resolution
position_index = build_position_index(collector.bindings, collector.unresolved_variables)
```

## Critical Implementation Details

### Gotcha 1: Circular Resolution
When resolving variable targets in build_position_index, you're using the index itself to resolve. Make sure variables can't reference other variables in a cycle.

### Gotcha 2: Scope-Aware Variable Resolution
Variables should follow the same scope rules as other bindings. A variable in an inner scope shadows one in an outer scope.

### Gotcha 3: Import Shadows
Variables can shadow imports too:
```python
from collections import Counter
Counter = MyCounter  # Variable shadows import
Counter()  # Should resolve to MyCounter, not the import
```

### Gotcha 4: dataclasses.replace
Since NameBinding is frozen (`@dataclass(frozen=True)`), you can't modify it directly. Use `dataclasses.replace()` to create a new instance with updated fields.

### Gotcha 5: Line Number Edge Cases
When resolving `calc = Calculator()`, the variable binding is at the same line as the reference to Calculator. Make sure your resolution handles same-line lookups correctly.

## Testing Your Implementation

1. **Primary Test**: Run `python test_prototype.py`
   - Should show line 48 is now resolved (no longer in unresolvable list)
   - `__module__.Calculator.compute` should have 1 call

2. **Check for Regressions**: The shadowing fixes should still work:
   - Lines 18, 28, 35, 40 should remain resolved

3. **Add Test Cases**: In test_shadowing_prototype.py, add:
```python
# Variable shadowing import
from datetime import datetime
datetime = MyDateTime  # Variable shadows import
datetime()  # Should resolve to MyDateTime

# Variable shadowing function
def processor():
    pass

processor = Calculator  # Variable shadows function
processor()  # Should resolve to Calculator.__init__
```

## Code Quality Notes

- This is prototype code, so use `--no-verify` for commits to bypass coverage requirements
- The prototype files intentionally don't have tests (testing is done via comparison)
- Focus on correctness over cleanliness - this is exploratory code

## Success Criteria

✅ Line 48 (`calc.compute()`) resolves correctly
✅ No regression in shadowing fixes (lines 18, 28, 35, 40)
✅ Variable shadowing works (variable shadows import/function)
✅ The comparison script shows improved results

## Common Issues You Might Hit

1. **TypeError with bisect**: The binary search compares tuples. Make sure your data structure is consistent.

2. **Infinite recursion**: When resolving variables, don't create cycles where resolution depends on itself.

3. **Missing imports**: You might need to add imports like `dataclasses` for `replace()`

4. **Attribute errors**: Remember that `extract_attribute_chain` expects ast.Attribute, not ast.Name

## Questions This Implementation Should Answer

1. Can variables shadow each other within the same scope?
2. How do we handle `calc = Calculator` (without parens) vs `calc = Calculator()`?
3. Should variables be included in the final PositionIndex or resolved away?
4. How do we handle variable reassignment at different lines?

## Final Note

The plan (Step 7) treats variable tracking as complex and deferrable, but it's actually essential for feature parity. Your implementation will prove that variable tracking should be part of the core architecture, not an optional enhancement.

Good luck! The prototype has already proven the architecture works - you're just filling in the missing piece that makes it feature-complete.
