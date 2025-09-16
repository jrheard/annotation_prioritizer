# Scope-Aware Variable Tracking Implementation Plan

## Executive Summary

This document outlines the implementation of scope-aware variable tracking to fix the **critical bug** where instance method calls are not counted. This is **Step 3 of 3** in our improvement sequence and represents the culmination of our accuracy improvements.

**The Critical Bug**: When `calc = Calculator()` is followed by `calc.add(5, 7)`, the method call is NOT counted because we don't track that `calc` is a Calculator instance.

**The Solution**: Track variable-to-type mappings with scope awareness to enable accurate method call resolution.

## Status: PENDING

**Prerequisites** (MUST be complete before starting):
1. ✅ Class Detection Improvements - Provides accurate class registry
2. ✅ Unresolvable Call Reporting - Provides transparency when tracking fails

## Problem Statement

### Current Behavior (BROKEN)
```python
class Calculator:
    def add(self, a, b):
        return a + b

def foo():
    calc = Calculator()  # Variable assignment - NOT tracked
    return calc.add(5, 7)  # Method call - NOT COUNTED (Critical bug!)
```

### Expected Behavior (FIXED)
```python
def foo():
    calc = Calculator()  # Track: calc -> Calculator instance
    return calc.add(5, 7)  # COUNTED as Calculator.add call
```

### Impact
- **Current**: Tool misses most method calls, severely undermining accuracy
- **Fixed**: Accurate method call counting for 99% of real-world patterns
- **Benefit**: Developers get reliable prioritization for type annotations

## Technical Design

### 1. Core Data Structure

```python
@dataclass(frozen=True)
class VariableType:
    """Type information for a variable in a specific scope."""
    class_name: str      # e.g., "Calculator" or "int"
    is_instance: bool    # True for instances, False for class itself

    # Optional fields for future extensibility
    module_path: str | None = None  # For imported types
    is_builtin: bool = False        # For str, int, list, etc.
```

### 2. Scope-Qualified Variable Tracking

Variables are tracked with scope-qualified keys to prevent contamination:

```python
# Key format: "scope.path.variable_name"
scoped_variables: dict[str, VariableType] = {
    "__module__.foo.calc": VariableType("Calculator", True),
    "__module__.bar.calc": VariableType("int", True),  # Different variable!
    "__module__.DEFAULT_CALC": VariableType("Calculator", True),  # Module-level
}
```

### 3. Variable Discovery Patterns

#### Pattern 1: Direct Instantiation
```python
calc = Calculator()  # Track: calc is Calculator instance
calc = Calculator    # Track: calc is Calculator class (not instance)
```

#### Pattern 2: Function Parameters (ALL types)
```python
def process(
    calc: Calculator,           # Regular parameter
    /,
    pos_only: Calculator,       # Positional-only
    *args: Calculator,          # Variadic positional
    keyword_only: Calculator,   # Keyword-only
    **kwargs: Calculator        # Variadic keyword
):
    # Track ALL of these in function scope
```

#### Pattern 3: Annotated Variables
```python
calc: Calculator = Calculator()  # With initialization
processor: DataProcessor        # Just annotation (track type, not instance)
result: int = calc.add(1, 2)   # Track result as int
```

#### Pattern 4: Module-Level Variables
```python
# At module level
DEFAULT_PROCESSOR = DataProcessor()  # Track at __module__ scope
SHARED_CALC: Calculator = Calculator()  # With annotation
```

### 4. String Annotations and Forward References

Leverage the existing two-pass analysis:

```python
# First pass: Collect all class definitions
# Second pass: Resolve string annotations

def foo(x: "Calculator"):  # String annotation
    return x.add(1, 2)     # Will resolve after second pass

def bar(calc: Calculator):  # Forward reference
    return calc.process()   # Works because we do two passes

class Calculator:  # Defined after use
    def process(self): ...
```

### 5. Updated Call Resolution Logic

```python
def _extract_call_name(self, node: ast.Call) -> str | None:
    func = node.func

    if isinstance(func, ast.Attribute):
        if isinstance(func.value, ast.Name):
            var_name = func.value.id

            # Build scope-qualified key
            scope_key = self._build_scope_key(var_name)

            # Check variable tracking
            if scope_key in self.scoped_variables:
                var_type = self.scoped_variables[scope_key]
                if var_type.is_instance:
                    # Resolve to class method
                    method_name = f"__module__.{var_type.class_name}.{func.attr}"
                    return method_name
                elif not var_type.is_instance:
                    # Class method/static method call
                    return f"__module__.{var_type.class_name}.{func.attr}"

            # Check parent scopes (module level only for now)
            module_key = f"__module__.{var_name}"
            if module_key in self.scoped_variables:
                var_type = self.scoped_variables[module_key]
                if var_type.is_instance:
                    return f"__module__.{var_type.class_name}.{func.attr}"

            # Can't resolve - mark as unresolvable
            self.unresolvable_calls.add(self._format_call_for_reporting(node))
            return None
```

## Implementation Steps

### Phase 1: Data Structures and Utilities (2 hours)

1. **Add VariableType to models.py**
   - Create frozen dataclass with class_name and is_instance
   - Add optional fields for future extensibility

2. **Create scope key builder utility**
   ```python
   def build_scope_key(scope_stack: list[Scope], var_name: str) -> str:
       """Build a scope-qualified variable key."""
       scope_parts = [scope.name for scope in scope_stack]
       return ".".join([*scope_parts, var_name])
   ```

3. **Add variable tracking to CallCountVisitor**
   - Add `scoped_variables: dict[str, VariableType] = {}`
   - Initialize in `__init__` with class_registry parameter

### Phase 2: Variable Discovery (3 hours)

1. **Implement assignment tracking**
   ```python
   def visit_Assign(self, node: ast.Assign) -> None:
       # Handle: calc = Calculator()
       if isinstance(node.value, ast.Call):
           class_name = self._extract_call_name(node.value)
           if class_name and class_name in self.class_registry.classes:
               # Track all targets as instances
               for target in node.targets:
                   if isinstance(target, ast.Name):
                       scope_key = self._build_scope_key(target.id)
                       self.scoped_variables[scope_key] = VariableType(
                           class_name=class_name.split(".")[-1],
                           is_instance=True
                       )
   ```

2. **Implement annotated assignment tracking**
   ```python
   def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
       # Handle: calc: Calculator = Calculator()
       if node.target and isinstance(node.target, ast.Name):
           type_name = self._extract_type_from_annotation(node.annotation)
           if type_name:
               scope_key = self._build_scope_key(node.target.id)
               # Determine if instance based on value
               is_instance = isinstance(node.value, ast.Call) if node.value else False
               self.scoped_variables[scope_key] = VariableType(
                   class_name=type_name,
                   is_instance=is_instance
               )
   ```

3. **Implement parameter tracking**
   ```python
   def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
       # ... existing scope management ...

       # Track parameters with type annotations
       for arg in node.args.args:
           if arg.annotation:
               type_name = self._extract_type_from_annotation(arg.annotation)
               if type_name:
                   scope_key = self._build_scope_key(arg.arg)
                   self.scoped_variables[scope_key] = VariableType(
                       class_name=type_name,
                       is_instance=True  # Parameters are instances
                   )

       # Track other parameter types (posonlyargs, kwonlyargs, etc.)
       # ...
   ```

### Phase 3: Type Extraction and String Annotations (2 hours)

1. **Create type extraction helper**
   ```python
   def _extract_type_from_annotation(self, annotation: ast.expr) -> str | None:
       """Extract type name from annotation node."""
       if isinstance(annotation, ast.Name):
           return annotation.id
       elif isinstance(annotation, ast.Constant):
           # String annotation like "Calculator"
           if isinstance(annotation.value, str):
               return annotation.value.strip('"\'')
       elif isinstance(annotation, ast.Attribute):
           # Handle module.ClassName annotations
           parts = []
           node = annotation
           while isinstance(node, ast.Attribute):
               parts.append(node.attr)
               node = node.value
           if isinstance(node, ast.Name):
               parts.append(node.id)
           return ".".join(reversed(parts))
       return None
   ```

2. **Handle forward references in second pass**
   - Store unresolved annotations during first pass
   - Resolve them after class registry is complete
   - Update scoped_variables with resolved types

### Phase 4: Call Resolution Integration (2 hours)

1. **Update _extract_call_name in CallCountVisitor**
   - Check scoped_variables for attribute access patterns
   - Fall back to parent scope (module only) if not found
   - Mark as unresolvable if variable type unknown

2. **Integrate with existing call counting**
   - Ensure resolved method calls are counted
   - Maintain backward compatibility with direct calls

3. **Update unresolvable call tracking**
   - When variable type can't be determined, add to unresolvable
   - Provide meaningful error messages

### Phase 5: Testing (3 hours)

1. **Unit Tests for VariableType**
   - Test frozen dataclass properties
   - Test equality and hashing

2. **Unit Tests for Variable Tracking**
   ```python
   def test_direct_instantiation_tracking():
       """Test that calc = Calculator() is tracked."""

   def test_parameter_annotation_tracking():
       """Test all parameter types are tracked."""

   def test_module_level_variable_tracking():
       """Test module-level variables are tracked."""

   def test_scope_isolation():
       """Test variables in different scopes don't interfere."""
   ```

3. **Integration Tests**
   ```python
   def test_bug_fix_instance_method_counting():
       """Verify the critical bug is fixed."""
       code = '''
       class Calculator:
           def add(self, a, b):
               return a + b

       def foo():
           calc = Calculator()
           return calc.add(5, 7)  # This MUST be counted
       '''
       # Assert Calculator.add has call_count = 1
   ```

4. **Edge Case Tests**
   - String annotations
   - Forward references
   - False positive prevention (calc = 5; calc + 7)
   - Unresolvable call integration

### Phase 6: Documentation and Cleanup (1 hour)

1. **Update project_status.md**
   - Mark variable tracking as COMPLETE
   - Update accuracy metrics
   - Document remaining limitations

2. **Update docstrings**
   - Document new parameters and methods
   - Add examples of tracked patterns

3. **Code cleanup**
   - Ensure all new code follows functional style
   - Run linting and formatting
   - Achieve 100% test coverage

## Testing Strategy

### Critical Success Tests

1. **The Bug Fix Test**
   ```python
   # THIS MUST PASS
   def test_instance_method_calls_are_counted():
       calc = Calculator()
       result = calc.add(5, 7)  # Count = 1
   ```

2. **Scope Isolation Test**
   ```python
   def foo():
       calc = Calculator()  # foo.calc
       calc.add(1, 2)       # Counted

   def bar():
       calc = 5             # bar.calc (different!)
       calc + 7             # NOT counted
   ```

3. **Parameter Type Test**
   ```python
   def process(calc: Calculator):
       return calc.add(1, 2)  # Counted
   ```

4. **Unresolvable Integration Test**
   ```python
   def mystery():
       unknown = get_something()  # Can't track
       unknown.method()           # Mark as unresolvable
   ```

### Test Coverage Requirements

- 100% line coverage (project requirement)
- All assignment patterns tested
- All parameter types tested
- Scope isolation verified
- String annotations tested
- Forward references tested
- False positive prevention verified

## Exclusions and Limitations

### Currently Not Implementing (Future Consideration)

1. **Nested Function Parent Scope Variables**
   ```python
   def outer():
       calc = Calculator()  # Parent scope
       def inner():
           return calc.add(1, 2)  # Won't track (yet)
   ```
   - Rationale: Adds complexity, not critical for initial fix
   - Status: Marked for future reconsideration

### Future Work (Documented in project_status.md)

1. **Class Attributes**
   ```python
   class Server:
       pool = ConnectionPool()  # Class-level
       def use(self):
           self.pool.get()      # Won't track yet
   ```

2. **Import Aliases**
   ```python
   from calculator import Calculator as Calc
   c = Calc()  # Won't track as Calculator yet
   ```

3. **Complex Types**
   - Union types (Foo | Bar)
   - Generic types (List[Calculator])
   - Type aliases

### Permanent Limitations

1. **Dynamic Behavior**
   - exec/eval generated code
   - Runtime type modifications
   - Metaclass magic

2. **Complex Decorators**
   - Property decorators might be reconsidered
   - Other decorators remain out of scope

## Success Metrics

The implementation is successful when:

1. ✅ **Bug Fixed**: Instance method calls ARE counted
2. ✅ **Accuracy**: 99% of common patterns work correctly
3. ✅ **No False Positives**: Non-method calls aren't counted
4. ✅ **Scope Safety**: Variables in different scopes don't interfere
5. ✅ **Transparency**: Unresolvable calls are properly reported
6. ✅ **Test Coverage**: 100% coverage maintained
7. ✅ **Code Quality**: All linting/formatting checks pass

## Implementation Checklist

- [ ] Phase 1: Data Structures and Utilities
  - [ ] Add VariableType to models.py
  - [ ] Create scope key builder
  - [ ] Add scoped_variables to CallCountVisitor

- [ ] Phase 2: Variable Discovery
  - [ ] Implement visit_Assign
  - [ ] Implement visit_AnnAssign
  - [ ] Track function parameters

- [ ] Phase 3: Type Extraction
  - [ ] Create type extraction helper
  - [ ] Handle string annotations
  - [ ] Implement forward reference resolution

- [ ] Phase 4: Call Resolution
  - [ ] Update _extract_call_name
  - [ ] Integrate with call counting
  - [ ] Update unresolvable tracking

- [ ] Phase 5: Testing
  - [ ] Write unit tests
  - [ ] Write integration tests
  - [ ] Verify bug fix
  - [ ] Test edge cases

- [ ] Phase 6: Documentation
  - [ ] Update project_status.md
  - [ ] Update docstrings
  - [ ] Clean up code

## Risk Assessment

### Low Risk
- Using existing scope infrastructure
- Building on completed prerequisites
- Conservative approach (accuracy over completeness)

### Medium Risk
- String annotation resolution complexity
- Forward reference handling
- Maintaining 100% test coverage

### Mitigation
- Start with simple cases, add complexity incrementally
- Write tests first for complex scenarios
- Use existing two-pass infrastructure

## Timeline

- **Total Estimate**: 11 hours of focused work
- **Priority**: IMMEDIATE (fixes critical bug)
- **Dependencies**: Class detection and unresolvable reporting MUST be complete

## Conclusion

This implementation fixes the critical bug where instance method calls are not counted, completing our three-part improvement sequence. By tracking variables with scope awareness, we enable accurate method call resolution while maintaining the project's conservative philosophy: accuracy over completeness.

The implementation leverages existing infrastructure (scope stack, class registry, two-pass analysis) and follows functional programming principles with immutable data structures. Upon completion, the tool will accurately count method calls for 99% of real-world Python patterns, providing developers with reliable type annotation prioritization.
