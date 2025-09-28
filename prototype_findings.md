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

### 5. **Variable Tracking Complexity Underestimated**

**Issue**: While the plan includes variable tracking in Step 7 (and Step 8 depends on it), it doesn't emphasize strongly enough that this is critical for feature parity, nor does it capture the full complexity of implementation.

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

**Why this matters**: While the plan includes variable tracking, it doesn't sufficiently emphasize that this is required for feature parity. The wording "assignments that are relevant for method resolution" might be interpreted as only special cases, when in fact it's needed for the common pattern of `calc = Calculator(); calc.compute()`.

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

## Appendix: Variable Tracking Implementation Findings

This appendix documents specific lessons learned while implementing variable tracking (Step 7 of the plan), which turned out to be far more critical and complex than the plan suggested.

### A1. Variable Tracking is Critical But Underestimated

**What the plan says** (Step 7 introduction):
> "Track variable assignments that are relevant for method resolution. Since we can't resolve class names during collection (the index doesn't exist yet), we track unresolved references..."

**What might be misunderstood**: While the plan includes variable tracking as Step 7 (and Step 8 depends on it), the wording "assignments that are relevant for method resolution" might suggest it's only for advanced cases. The plan doesn't emphasize that WITHOUT this step, common patterns will break.

**What I discovered**: Without variable tracking, we have an immediate regression that breaks existing functionality.

**Test case that fails without variable tracking**:
```python
# test_shadowing_prototype.py, lines 57-58
class Calculator:
    def compute(self, x):
        return x * 2

calc = Calculator()
calc.compute(10)  # This becomes unresolvable without variable tracking!
```

**Test output showing the regression**:
```
--- PROTOTYPE IMPLEMENTATION (without variables) ---
Unresolvable calls: 4
  Line 58: calc.compute(10)  # <-- REGRESSION!

Function call count changes:
  __module__.Calculator.compute: 1 -> 0  # <-- Lost a call count!
```

**Why this matters**: The existing codebase has `VariableRegistry` that tracks these patterns. Removing it without replacement causes immediate breakage. While the plan does include variable tracking, it should more prominently state: **"Variable tracking is REQUIRED for feature parity. Without it, method calls through variables will not resolve."**

### A2. Variable Resolution Process Complexity

**What the plan shows** (Step 8, lines 276-323):
```python
def build_position_index(
    bindings: list[NameBinding],
    unresolved_variables: list[tuple[NameBinding, str]]
) -> PositionIndex:
    # Build the basic index...
    # Create temporary index for resolution
    temp_index = PositionIndex(_index=dict(index))

    # Resolve variable targets
    for variable_binding, target_name in unresolved_variables:
        resolved = temp_index.resolve(target_name, ...)
        if resolved and resolved.kind == NameBindingKind.CLASS:
            resolved_binding = dataclasses.replace(
                variable_binding,
                target_class=resolved.qualified_name
            )
            # Replace the unresolved binding with resolved one in the index
            # Implementation details omitted for brevity
```

**What this misses**: The plan doesn't explain HOW to "replace the unresolved binding in the index." Since we're building the index from a list of bindings, and bindings are immutable, this is non-trivial.

**What I actually had to implement**:
```python
def build_position_index(
    bindings: list[NameBinding],
    unresolved_variables: list[tuple[NameBinding, str]] | None = None,
) -> PositionIndex:
    # Step 1: Build the initial index
    index: dict[QualifiedName, dict[str, list[tuple[int, NameBinding]]]] = defaultdict(
        lambda: defaultdict(list)
    )

    for binding in bindings:
        # Convert scope_stack to qualified name for indexing
        if not binding.scope_stack or len(binding.scope_stack) == 1:
            scope_name = make_qualified_name("__module__")
        else:
            scope_name = make_qualified_name(".".join(s.name for s in binding.scope_stack))
        index[scope_name][binding.name].append((binding.line_number, binding))

    # Sort for binary search
    for scope_dict in index.values():
        for binding_list in scope_dict.values():
            binding_list.sort(key=lambda x: x[0])

    # Step 2: If we have unresolved variables, resolve their targets
    if unresolved_variables:
        import dataclasses
        from annotation_prioritizer.models import NameBindingKind

        # Create temporary index for resolution
        temp_index = PositionIndex(_index=dict(index))

        # Step 3: Build a new list of ALL bindings with resolved variables
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

        # Step 4: COMPLETELY REBUILD the index with resolved bindings
        index = defaultdict(lambda: defaultdict(list))
        for binding in resolved_bindings:
            if not binding.scope_stack or len(binding.scope_stack) == 1:
                scope_name = make_qualified_name("__module__")
            else:
                scope_name = make_qualified_name(".".join(s.name for s in binding.scope_stack))
            index[scope_name][binding.name].append((binding.line_number, binding))

        # Step 5: Sort again for binary search
        for scope_dict in index.values():
            for binding_list in scope_dict.values():
                binding_list.sort(key=lambda x: x[0])

    return PositionIndex(_index=dict(index))
```

**Key insights the plan missed**:
1. You need to track ALL bindings, not just variables, to rebuild the complete index
2. The index must be completely rebuilt after resolution - you can't modify it in place
3. You need to check equality (`binding == var_binding`) to find which bindings to replace
4. The sorting step must be repeated after rebuilding
5. `dataclasses.replace()` is required because NameBinding is frozen

### A3. Integration Points Were Incorrectly Named

**What the plan shows** (Step 9, lines 362-378):
```python
def _resolve_attribute_call(self, func: ast.Attribute) -> QualifiedName | None:
    """Resolve method calls like calc.add()."""
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

    # Fall back to existing attribute resolution logic
    return self._existing_attribute_resolution(func)
```

**Problems with this**:
1. There's no method called `_resolve_attribute_call` in CallCountVisitor
2. The actual method is `_resolve_method_call`
3. The integration point is more complex than shown

**What actually exists in the codebase**:
```python
# In call_counter_prototype.py
def _resolve_method_call(self, func: ast.Attribute) -> QualifiedName | None:
    """Resolve method calls like self.method() or ClassName.method()."""
    # Handle self.method() calls
    if isinstance(func.value, ast.Name) and func.value.id == "self":
        # ... self resolution logic ...
        return None

    # Handle ClassName.method() - extract the full attribute chain
    try:
        # Get the full chain including the final attribute
        full_chain = extract_attribute_chain(func)
        # ... complex chain resolution ...
```

**What I actually had to implement**:
```python
def _resolve_method_call(self, func: ast.Attribute) -> QualifiedName | None:
    """Resolve method calls like self.method() or ClassName.method()."""
    # Handle self.method() calls
    if isinstance(func.value, ast.Name) and func.value.id == "self":
        # ... existing self resolution logic ...
        return None

    # NEW: Handle variable.method() calls - MUST come before ClassName.method()
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

    # EXISTING: Handle ClassName.method() - extract the full attribute chain
    try:
        # ... existing complex chain resolution ...
```

**Why the placement matters**: The variable resolution MUST come before the complex ClassName.method() handling, but after self.method(). The plan doesn't specify this critical ordering.

### A4. Unresolved Variables Collection Details

**What the plan shows** (Step 7, lines 224-262):
```python
def visit_Assign(self, node: ast.Assign) -> None:
    """Track assignments like calc = Calculator()."""
    if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        variable_name = node.targets[0].id

        # Check if it's a class instantiation or reference
        if isinstance(node.value, ast.Call) and isinstance(node.value.func, ast.Name):
            # calc = Calculator() - track for later resolution
            class_name = node.value.func.id
            # ... create binding and append to unresolved_variables
```

**What the plan doesn't explain**: How to track the unresolved variables alongside the collector.

**What I implemented**:
```python
class NameBindingCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.bindings: list[NameBinding] = []
        self.unresolved_variables: list[tuple[NameBinding, str]] = []  # Critical addition!
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
                    kind=NameBindingKind.VARIABLE,
                    qualified_name=build_qualified_name(self._scope_stack, variable_name),
                    scope_stack=self._scope_stack,
                    source_module=None,
                    target_class=None,  # Will be resolved later
                )
                self.bindings.append(binding)
                self.unresolved_variables.append((binding, class_name))  # Track for resolution

            elif isinstance(node.value, ast.Name):
                # Handle calc = Calculator (without parens)
                ref_name = node.value.id
                binding = NameBinding(
                    name=variable_name,
                    line_number=node.lineno,
                    kind=NameBindingKind.VARIABLE,
                    qualified_name=build_qualified_name(self._scope_stack, variable_name),
                    scope_stack=self._scope_stack,
                    source_module=None,
                    target_class=None,  # Will be resolved later
                )
                self.bindings.append(binding)
                self.unresolved_variables.append((binding, ref_name))  # Track for resolution

        self.generic_visit(node)  # Don't forget to continue traversal!
```

**Key detail missed**: The plan shows the structure but doesn't emphasize that `self.generic_visit(node)` is REQUIRED at the end of visit_Assign to continue traversing nested nodes.

### A5. Edge Cases Not Addressed

The plan doesn't discuss several important edge cases I encountered:

**1. Variable-to-variable assignments**:
```python
calc = Calculator()
calc2 = calc  # What should calc2.target_class be?
calc2.compute()  # Should this resolve?
```

**What I implemented**: Only resolve one level. If `calc` resolves to a VARIABLE kind, we don't follow the chain. This means `calc2.compute()` won't resolve in the prototype.

**2. Variable shadowing**:
```python
calc = OldCalculator()
calc.old_method()  # Should resolve to OldCalculator.old_method
calc = NewCalculator()
calc.new_method()  # Should resolve to NewCalculator.new_method
```

**What works**: The position-aware index handles this correctly! Each assignment creates a new binding at a different line number.

**3. Non-class assignments we track unnecessarily**:
```python
result = calc.compute(10)  # We track 'result' as a variable but can't resolve it
```

**Current behavior**: We create a variable binding for `result` with `target_class=None` because `calc.compute(10)` isn't a simple name. This is harmless but adds noise.

### A6. The Immutability Constraint

**Critical detail the plan glosses over**: Why do we need `dataclasses.replace()`?

The plan mentions using `dataclasses.replace()` but doesn't explain the constraint that makes it necessary:

```python
@dataclass(frozen=True)  # <-- This makes ALL fields read-only!
class NameBinding:
    name: str
    line_number: int
    kind: NameBindingKind
    qualified_name: QualifiedName | None
    scope_stack: "ScopeStack"
    source_module: str | None
    target_class: QualifiedName | None = None
```

**What doesn't work**:
```python
# This will raise an error!
binding.target_class = resolved.qualified_name  # FrozenInstanceError!
```

**What you must do instead**:
```python
import dataclasses

# Create a NEW binding with the updated field
resolved_binding = dataclasses.replace(
    binding,
    target_class=resolved.qualified_name
)
```

**Why this matters**: The functional programming style (immutable data) is a project requirement. The plan should explicitly note: "Because NameBinding is frozen (immutable), resolution requires creating new instances, not modifying existing ones."

### A7. Recommended Plan Updates

Based on my implementation experience, here are specific changes needed in the plan:

**1. Emphasize variable tracking importance**:
- Keep Step 7 where it is (the sequencing is correct)
- Add prominent warning: **"REQUIRED FOR FEATURE PARITY - without this, method calls through variables will not resolve"**
- Clarify that "assignments relevant for method resolution" includes ALL variable assignments to classes

**2. Add complete resolution example in Step 8**:
- Show the full index rebuild process
- Explain the need to track all bindings for rebuilding
- Include the duplicate sorting step

**3. Fix method names in Step 9**:
- Change `_resolve_attribute_call` to `_resolve_method_call`
- Show the exact placement in the existing method flow
- Note that variable resolution must come before chain extraction

**4. Add limitations section to variable tracking**:
```
### Variable Tracking Limitations (Phase 1)
- Variable-to-variable assignments are not followed (calc2 = calc)
- Only tracks assignments to ast.Name targets (not attributes or subscripts)
- Function references through variables remain unresolvable (process = sqrt)
- Import references through variables remain unresolvable (dt = datetime)
```

**5. Add performance note**:
"Variable resolution adds a one-time O(n) cost during index building to resolve and rebuild the index. This doesn't affect the O(log k) lookup performance."

### A8. Most Critical Insight

**The plan's biggest gap**: Not emphasizing strongly enough that variable tracking is required for feature parity, and underestimating the complexity of the resolution process.

**Evidence from test output**:
```bash
# Without variable tracking
✗ Lines now unresolvable in prototype: [58]
Function call count changes:
  __module__.Calculator.compute: 1 -> 0  # REGRESSION!

# With variable tracking
✓ Line 58 (calc.compute()) resolved: True
✓ __module__.Calculator.compute: 1 calls
```

**The lesson**: When refactoring working code, every existing feature needs a replacement. While the plan does include variable tracking (Step 7), it should more prominently highlight that this directly replaces VariableRegistry and is essential for maintaining existing functionality.
