# Prototype Findings: Single Collector Architecture

## Executive Summary

The prototype successfully validates the core approach described in `plans/pending/single-collector-position-aware-2025-09-26.md`. The position-aware resolution using binary search correctly fixes the shadowing bug (issue #31) while reducing AST traversal passes from 5+ to 2. However, the plan had several areas that required clarification during implementation.

## Plan Strengths

### 1. **Clear Problem Definition**
The plan excellently describes the shadowing bug with concrete examples, making it easy to understand what needs to be fixed and write validation tests.

### 2. **Well-Defined Data Structures**
The `NameBinding` and `PositionIndex` structures were described clearly enough to implement directly from the plan with minimal modifications.

### 3. **Phased Approach**
The distinction between Phase 1 (single-file) and Phase 2 (multi-file) helped focus the prototype on the essential problem without getting lost in cross-module complexity.

### 4. **Comprehensive Test Strategy**
The plan's emphasis on testing shadowing scenarios from issue #31 provided clear success criteria.

## Plan Weaknesses & Discoveries

### 1. **Scope Qualified Name Building (Critical Gap)**

**Issue**: The plan shows `build_qualified_name(binding.scope_stack)` in multiple places, but this function signature doesn't exist in the codebase.

**What the plan assumed** (Step 8, line 275):
```python
def build_position_index(bindings: list[NameBinding]) -> PositionIndex:
    for binding in bindings:
        # Convert scope_stack to qualified name for indexing
        scope_name = build_qualified_name(binding.scope_stack)
        index[scope_name][binding.name].append((binding.line_number, binding))
```

**The actual function signature**:
```python
def build_qualified_name(scope_stack: ScopeStack, name: str) -> QualifiedName:
    """Build a qualified name from scope stack AND a name."""
```

**What I had to figure out**:
The existing `build_qualified_name()` always requires a `name` parameter to append to the scope. When you just want the scope's own qualified name (not appending anything), you need completely different logic:

```python
# For empty or module-only scope:
if not binding.scope_stack or len(binding.scope_stack) == 1:
    scope_name = make_qualified_name("__module__")
else:
    # Manually concatenate scope names
    scope_name = make_qualified_name(".".join(s.name for s in binding.scope_stack))
```

**Why this matters**: This pattern appears in at least 3 critical places:
1. Building the position index (storing bindings by scope)
2. Resolving names (looking up in each scope)
3. Creating qualified names for bindings

The plan's pseudocode wouldn't have worked without discovering this gap. A helper function like `get_scope_qualified_name(scope_stack: ScopeStack) -> QualifiedName` should have been specified in the plan.

### 2. **Circular Import Dependencies**

**Issue**: The plan adds `NameBinding` to `models.py` with a `ScopeStack` field, but doesn't address the circular import between `models.py` and `scope_tracker.py`.

**The circular dependency**:
- `models.py` needs `ScopeStack` type for the `NameBinding.scope_stack` field
- `scope_tracker.py` imports `Scope` and other types from `models.py`
- This creates `models.py` → `scope_tracker.py` → `models.py` circular import

**Solution I implemented** (workaround):
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from annotation_prioritizer.scope_tracker import ScopeStack
```

**Better solution** (discovered during review):
Move the type alias definition to `models.py`:
```python
# In models.py
type ScopeStack = tuple[Scope, ...]

# Then scope_tracker.py imports it:
from annotation_prioritizer.models import ScopeStack
```

This is cleaner because:
- `ScopeStack` is fundamentally a data model type
- It belongs with `Scope` in `models.py`
- Eliminates the circular dependency entirely
- No need for TYPE_CHECKING tricks

The plan should have recognized this structural issue and specified where type definitions should live.

### 3. **Method Call Resolution Complexity**

**Issue**: The plan's Step 9 shows a simplified `_resolve_attribute_call` implementation but doesn't address several critical complexities.

**What the plan showed**:
```python
def _resolve_attribute_call(self, func: ast.Attribute) -> QualifiedName | None:
    if isinstance(func.value, ast.Name):
        # Look up the variable
        binding = self._position_index.resolve(func.value.id, ...)
        if binding and binding.kind == NameBindingKind.VARIABLE and binding.target_class:
            return make_qualified_name(f"{binding.target_class}.{func.attr}")
```

**What I discovered during implementation**:

1. **AST Node Type Mismatch**: The existing `extract_attribute_chain()` function expects an `ast.Attribute` node, but when you have `calc.compute()`, you need to handle:
   - `func` is the entire `ast.Attribute` for `calc.compute`
   - `func.value` could be an `ast.Name` (simple case: `calc`)
   - `func.value` could be another `ast.Attribute` (nested case: `outer.inner.method`)

2. **Chain Extraction Complexity**: I had to write different logic for different cases:
   ```python
   # Simple case: ClassName.method()
   if isinstance(func.value, ast.Name):
       chain = (func.value.id,)

   # Nested case: Outer.Inner.method()
   elif isinstance(func.value, ast.Attribute):
       chain = extract_attribute_chain(func.value)

   # But wait! extract_attribute_chain(func.value) fails if func.value is ast.Name
   # So we need try/except blocks and fallback logic
   ```

3. **Nested Class Instantiation Detection**: The plan doesn't explain how to distinguish between:
   - `Calculator.compute()` - a method call on a class
   - `Outer.Inner()` - instantiation of a nested class

   This required checking if the resolved name (minus the final attribute) is in the known classes set.

4. **Error Handling**: `extract_attribute_chain()` can throw `AssertionError` for complex expressions like `foo()[0].bar`, which the plan doesn't mention. This required wrapping in try/except blocks.

### 4. **Integration Points Underspecified**

**Issue**: The plan shows `CallCountVisitor` using `PositionIndex` but doesn't explain how it identifies classes for `__init__` resolution without `ClassRegistry`.

**What the plan showed** (Step 9):
```python
class CallCountVisitor(ast.NodeVisitor):
    def __init__(self, ..., position_index: PositionIndex, ...):
        self._position_index = position_index
        # Remove old registry dependencies
```

**The missing piece**: When resolving `Calculator()`, the visitor needs to know that `Calculator` is a class (not a function) to append `.__init__`. The plan removes `ClassRegistry` but doesn't explain the replacement.

**What I had to implement**:
```python
# In analyze_ast_prototype:
# Extract known classes from the bindings
known_classes = {
    binding.qualified_name
    for binding in collector.bindings
    if binding.kind == NameBindingKind.CLASS and binding.qualified_name
}

# In CallCountVisitor:
def set_known_classes(self, classes: set[QualifiedName]) -> None:
    self._known_classes = classes

# During resolution:
if binding.kind == NameBindingKind.CLASS and binding.qualified_name:
    return make_qualified_name(f"{binding.qualified_name}.__init__")
```

**Why this gap matters**: Without this, class instantiations wouldn't be counted properly. The plan should have specified how class identification would work post-refactor.

### 5. **Variable Tracking Deferred But Critical**

**Issue**: The plan defers variable tracking to Step 7, presenting it as optional for the initial implementation. However, this causes immediate regressions.

**What the plan says** (Step 7 description):
```
Track variable assignments that are relevant for method resolution. Since we can't
resolve class names during collection (the index doesn't exist yet), we track
unresolved references...
```

**The regression this causes**:
```python
# test_shadowing_prototype.py, lines 57-58
calc = Calculator()
calc.compute(10)  # Previously resolved, now unresolvable
```

**Current implementation**: The existing codebase has `VariableRegistry` that tracks variable types, allowing `calc.compute()` to resolve to `Calculator.compute`.

**Prototype limitation**: Without variable tracking, the prototype marks this as unresolvable, showing as a regression in the test output:
```
✗ Lines now unresolvable in prototype: [48]
Function call count changes:
  __module__.Calculator.compute: 1 -> 0
```

**Why this matters**: The plan presents variable tracking as a "nice to have" enhancement, but it's actually required for feature parity. Any production implementation must include it from the start or risk breaking existing functionality.

## Inaccuracies in the Plan

### 1. **Binary Search Implementation**

**What the plan suggested** (Step 8):
```python
# Binary search for the latest binding before this line
idx = bisect.bisect_left(bindings, (line, None))
```

**The assumption**: That you can pass `(line, None)` to bisect and it will work correctly.

**The reality**: Python's `bisect` compares tuples element by element. When it compares `(line, None)` with `(line_number, binding)`, it works for the line number, but if line numbers match, it tries to compare `None` with a `NameBinding` object, which could cause issues.

**What actually works**:
```python
# The implementation relies on tuples comparing left-to-right
idx = bisect.bisect_left(bindings, (line, None))
# This works because we want all bindings with line_number < line
# But it's fragile - if we had bindings at the exact same line, comparison would fail
```

**Better approach** (not implemented in prototype):
```python
# Use key function to avoid comparing bindings
from operator import itemgetter
line_numbers = [line_num for line_num, _ in bindings]
idx = bisect.bisect_left(line_numbers, line)
```

The plan's approach technically works but is more fragile than implied.

### 2. **Performance Claims**

**What the plan claims** (Overview section):
> "Simplifies codebase by eliminating 5 separate visitors and their registries"
> "Performance: Reduced from 5+ AST passes to 2"

**Current implementation AST passes**:
1. `ImportDiscoveryVisitor` - finds imports
2. `ClassDiscoveryVisitor` - finds classes
3. `VariableDiscoveryVisitor` - tracks variable assignments
4. `FunctionDefinitionVisitor` - extracts function signatures
5. `CallCountVisitor` - counts function calls

**Prototype AST passes**:
1. `NameBindingCollector` - replaces visitors 1-3
2. `ClassRegistry` building - still needed for compatibility with `FunctionDefinitionVisitor`
3. `FunctionDefinitionVisitor` - unchanged
4. `CallCountVisitorPrototype` - counts calls

**The discrepancy**: The prototype achieves 4 passes (not 2), and we still build `ClassRegistry` for backward compatibility. The plan's claim of "2 passes" assumes:
- `FunctionDefinitionVisitor` would be merged into `NameBindingCollector`
- All legacy code would be removed

But Step 12 keeps `FunctionDefinitionVisitor` separate, contradicting the "2 passes" claim. The realistic improvement is 5 passes → 3-4 passes, not 5 → 2.

## What I Wish I Knew Before Starting

1. **Scope name building complexity** - The plan incorrectly assumes `build_qualified_name(scope_stack)` exists. Should have specified:
   - A new helper function `get_scope_qualified_name(scope_stack) -> QualifiedName`
   - Or shown the manual string concatenation logic required

2. **Type definition locations** - The plan should have specified:
   - Move `ScopeStack` type alias to `models.py` to avoid circular imports
   - Or create a separate `types.py` module for shared type definitions

3. **Test coverage exemptions** - The plan doesn't clarify:
   - Should prototype code be excluded from coverage requirements?
   - How to handle pre-commit hooks that enforce 100% coverage?
   - Whether to use `# pragma: no cover` or `--no-verify` for commits

4. **extract_attribute_chain limitations** - The plan should have warned:
   - This function only accepts `ast.Attribute` nodes, not `ast.Name`
   - It throws `AssertionError` for complex expressions
   - Different logic needed for simple vs. nested attribute access

5. **Class identification mechanism** - The plan removes `ClassRegistry` in Step 9 but doesn't specify:
   - How to track which names are classes vs functions
   - The need to extract and pass known classes separately
   - Impact on `__init__` resolution

6. **Variable tracking is not optional** - The plan presents Step 7 as deferrable but should have marked it as required for feature parity.

## Recommendations for Full Implementation

1. **Move type definitions first** (new Step 0):
   ```python
   # In models.py
   type ScopeStack = tuple[Scope, ...]
   ```
   This prevents the circular import issue before it starts.

2. **Add scope utility functions** (new Step 1.5):
   ```python
   def get_scope_qualified_name(scope_stack: ScopeStack) -> QualifiedName:
       """Convert a scope stack to its qualified name."""
       if not scope_stack or len(scope_stack) == 1:
           return make_qualified_name("__module__")
       return make_qualified_name(".".join(s.name for s in scope_stack))
   ```

3. **Implement variable tracking immediately** (merge with Step 3):
   - Don't defer to Step 7
   - Include the unresolved_variables tracking from the start
   - This prevents regressions and reduces test churn

4. **Keep `NameBinding.kind` check in resolution**:
   ```python
   # Always check the binding kind before using qualified_name
   if binding.kind == NameBindingKind.CLASS:
       return make_qualified_name(f"{binding.qualified_name}.__init__")
   elif binding.kind == NameBindingKind.FUNCTION:
       return binding.qualified_name
   ```

5. **Create test utilities for the migration**:
   ```python
   def compare_implementations(ast, source):
       """Run both old and new implementations, assert identical results."""
       old_result = analyze_ast(ast, source)
       new_result = analyze_ast_with_position_index(ast, source)
       assert_equivalent_results(old_result, new_result)
   ```

6. **Phase the CallCountVisitor update** (split Step 9):
   - Step 9a: Add PositionIndex parameter but keep registries
   - Step 9b: Use PositionIndex for direct calls only
   - Step 9c: Use PositionIndex for method calls
   - Step 9d: Remove registry dependencies

## Conclusion

The plan is fundamentally sound and the architecture works as designed. The prototype proves that position-aware resolution with binary search correctly fixes the shadowing bug. However, the plan underestimated implementation complexity in several areas, particularly around scope name management and method resolution. These findings should inform the full implementation to avoid the pitfalls discovered during prototyping.
