# Scope-Aware Variable Tracking Implementation Plan

**Date**: 2025-09-16
**Priority**: Critical
**Prerequisites**: Complete both class-detection-improvements-2025-09-16.md and unresolvable-call-reporting-2025-09-16.md first
**Implementation Order**: This is step 3 of 3 in the single-file accuracy improvement sequence
**Timeline**: These improvements are for immediate implementation to achieve very accurate single-file analysis. Directory-wide analysis will begin in a few weeks.

## Overview

This plan implements scope-aware variable tracking to fix the critical instance method call counting bug where calls like `calc.add()` are not being counted. The scope infrastructure (Scope/ScopeKind) is already implemented and provides the foundation for this enhancement.

## Problem Statement

### The Critical Bug

Instance method calls through variables are not being counted:

```python
class Calculator:
    def add(self, a, b):
        return a + b

def foo():
    calc = Calculator()
    return calc.add(5, 7)  # This call is NOT being counted!
```

**Current behavior:**
- AST sees: `calc.add()` where `calc` is just a variable name
- Parser expects: `__module__.Calculator.add` as the qualified name
- Result: No match → call count = 0

### Root Cause

The call counter lacks variable type tracking. It cannot resolve `calc.add()` to `Calculator.add` because it doesn't know that `calc` is an instance of `Calculator`.

## Solution Design

### Core Approach: Scoped Variable Tracking

Track variable-to-type mappings using fully qualified scope names to prevent cross-scope contamination:

- **Scope isolation**: `"scope.varname"` → `"ClassName"` mapping
- **Multiple tracking sources**: Direct instantiation, parameter annotations, annotated variables
- **Conservative resolution**: Only track what we can confidently determine

### Scope Naming Convention

Every variable gets a unique qualified name based on its scope:
- Module-level: `"__module__.variable_name"`
- Function-level: `"function_name.variable_name"`
- Nested functions: `"outer_function.inner_function.variable_name"`

This ensures complete isolation between scopes while maintaining simplicity.

## Prerequisites

This implementation depends on two prerequisite plans that must be completed first:

### 1. Class Detection Improvements (class-detection-improvements-2025-09-16.md)

**Why Required**: The variable tracking needs to identify when `Calculator()` is a class constructor vs. a function call. The current `name[0].isupper()` heuristic has significant limitations.

**Expected Deliverables**:
- AST-based class registry (`visit_ClassDef` tracking)
- Import-aware class detection (`visit_Import`, `visit_ImportFrom`)
- Built-in type registry for standard Python types
- Confidence-scored class detection replacing naive uppercase checks

### 2. Unresolvable Call Reporting (unresolvable-call-reporting-2025-09-16.md)

**Why Required**: We need infrastructure to distinguish between resolved and unresolvable calls before adding variable tracking.

**Expected Deliverables**:
- `CallCountResult` data model in `models.py`
- Updated `count_function_calls()` return type
- Modified `analyzer.py` to handle `CallCountResult`
- Reporting of unresolvable call counts and examples

## Implementation Steps

### Step 1: Enhance CallCountVisitor Data Structures

**File**: `src/annotation_prioritizer/call_counter.py`

Add scope-aware variable tracking to the existing visitor:

```python
class CallCountVisitor(ast.NodeVisitor):
    def __init__(self, known_functions: tuple[FunctionInfo, ...]) -> None:
        super().__init__()
        self.call_counts: dict[str, int] = {func.qualified_name: 0 for func in known_functions}

        # Existing scope infrastructure (already implemented)
        self._scope_stack: list[Scope] = [Scope(kind=ScopeKind.MODULE, name="__module__")]

        # NEW: Scope-aware variable tracking
        self.scoped_variables: dict[str, str] = {}  # "scope.varname" -> "ClassName"

    def _get_current_scope(self) -> str:
        """Get the fully qualified scope name."""
        scope_names = [scope.name for scope in self._scope_stack if scope.kind != ScopeKind.MODULE]
        if scope_names:
            return ".".join(scope_names)
        return "__module__"
```

### Step 2: Track Parameter Type Annotations

Extend the existing `visit_FunctionDef` to extract parameter type information:

```python
@override
def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
    """Visit function definition to track scope and parameter types."""
    self._scope_stack.append(Scope(kind=ScopeKind.FUNCTION, name=node.name))
    scope = self._get_current_scope()

    # Track all parameter type annotations
    all_args = []
    all_args.extend(node.args.posonlyargs)  # Positional-only (before /)
    all_args.extend(node.args.args)         # Regular parameters
    all_args.extend(node.args.kwonlyargs)   # Keyword-only (after *)

    for arg in all_args:
        if arg.annotation:
            param_type = self._extract_type_from_annotation(arg.annotation)
            if param_type:
                self.scoped_variables[f"{scope}.{arg.arg}"] = param_type

    # Intentional limitation: *args and **kwargs annotations not tracked
    # These are rarely annotated and would require complex access pattern analysis

    self.generic_visit(node)
    self._scope_stack.pop()

# Also handle async functions
visit_AsyncFunctionDef = visit_FunctionDef
```

### Step 3: Track Variable Assignments

Add assignment tracking to detect direct instantiation and annotated variables:

```python
@override
def visit_Assign(self, node: ast.Assign) -> None:
    """Track variable assignments to detect type information."""
    # Handle single target assignments: calc = Calculator()
    if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        var_name = node.targets[0].id
        class_name = self._extract_constructor_name(node.value)
        if class_name:
            scope = self._get_current_scope()
            self.scoped_variables[f"{scope}.{var_name}"] = class_name

    self.generic_visit(node)

@override
def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
    """Track annotated assignments like 'calc: Calculator = ...'."""
    if isinstance(node.target, ast.Name):
        var_name = node.target.id
        type_name = self._extract_type_from_annotation(node.annotation)
        if type_name:
            scope = self._get_current_scope()
            self.scoped_variables[f"{scope}.{var_name}"] = type_name

    self.generic_visit(node)
```

### Step 4: Type Extraction Helper Methods

Implement robust type extraction using the class detection improvements:

```python
def _extract_type_from_annotation(self, annotation: ast.expr) -> str | None:
    """Extract type name from annotation node using improved class detection."""
    # Handle simple name annotations: Calculator
    if isinstance(annotation, ast.Name):
        if self._is_known_class(annotation.id):
            return annotation.id

    # Handle string annotations (forward references): "Calculator"
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        annotation_str = annotation.value.strip()
        if annotation_str.isidentifier() and self._is_known_class(annotation_str):
            return annotation_str

    # Complex annotations not supported
    return None

def _extract_constructor_name(self, node: ast.expr) -> str | None:
    """Extract class name from constructor call using improved class detection."""
    # Handle: ClassName()
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        class_name = node.func.id
        if self._is_known_class(class_name):
            return class_name

    # Handle: module.ClassName() - extract just ClassName
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        class_name = node.func.attr
        if self._is_known_class(class_name):
            return class_name

    return None

def _is_known_class(self, name: str) -> bool:
    """Check if name is a known class using enhanced class detection."""
    # This method will be implemented by the class-detection-improvements prerequisite
    # For now, placeholder implementation:
    return name in self._class_registry or name[0].isupper()
```

### Step 5: Enhanced Call Resolution

Update the existing `_extract_call_name` method to use variable tracking:

```python
def _extract_call_name(self, node: ast.Call) -> str | None:
    """Extract the qualified name of the called function with variable resolution."""
    func = node.func

    # Direct function calls: function_name() (existing logic unchanged)
    if isinstance(func, ast.Name):
        return self._resolve_function_call(func.id)

    # Method calls: obj.method_name()
    if isinstance(func, ast.Attribute):
        # Self method calls: self.method_name() (existing logic unchanged)
        if isinstance(func.value, ast.Name) and func.value.id == "self":
            scope_names = [scope.name for scope in self._scope_stack if scope.kind != ScopeKind.FUNCTION]
            return ".".join([*scope_names, func.attr])

        # NEW: Instance method calls via variables
        if isinstance(func.value, ast.Name):
            var_name = func.value.id
            scope = self._get_current_scope()

            # Try current scope first
            scoped_var = f"{scope}.{var_name}"
            if scoped_var in self.scoped_variables:
                class_name = self.scoped_variables[scoped_var]
                return f"__module__.{class_name}.{func.attr}"

            # Try module scope (for module-level variables)
            module_var = f"__module__.{var_name}"
            if module_var in self.scoped_variables:
                class_name = self.scoped_variables[module_var]
                return f"__module__.{class_name}.{func.attr}"

            # Static/class method calls: ClassName.method_name() (existing logic)
            if self._is_known_class(var_name):
                return f"__module__.{var_name}.{func.attr}"

            # Unknown variable type - unresolvable
            return None

        # Complex qualified calls (existing logic unchanged)
        if isinstance(func.value, ast.Attribute):
            return f"__module__.{func.attr}"

    return None
```

### Step 6: Integration with Existing Scope Infrastructure

The implementation leverages the existing scope infrastructure without modification:

- **Scope tracking**: Uses existing `_scope_stack` and scope visitor methods
- **Qualified name generation**: Builds on existing patterns
- **Function resolution**: Extends existing `_resolve_function_call` method

## Comprehensive Test Specifications

### Test Categories

#### 1. Scope Isolation Tests

**Purpose**: Verify variables in different scopes don't contaminate each other

```python
def test_scope_isolation():
    """Variables with same name in different functions stay separate."""
    code = """
class Calculator:
    def add(self, x, y): return x + y

class Processor:
    def process(self): pass

def foo():
    calc = Calculator()
    calc.add(1, 2)  # Should count for Calculator.add

def bar():
    calc = Processor()  # Same variable name, different type!
    calc.process()  # Should count for Processor.process
"""
    # Verify Calculator.add == 1, Processor.process == 1
```

#### 2. Parameter Annotation Tests

**Purpose**: Verify all parameter types are tracked correctly

```python
def test_parameter_types_comprehensive():
    """All parameter annotation types should be tracked."""
    code = """
class Calculator:
    def add(self, x, y): return x + y

def regular_param(calc: Calculator):
    return calc.add(1, 2)  # Should be counted

def positional_only(calc: Calculator, /):
    return calc.add(3, 4)  # Should be counted

def keyword_only(*, calc: Calculator):
    return calc.add(5, 6)  # Should be counted

def mixed_params(a: int, calc: Calculator, /, *, flag: bool):
    return calc.add(7, 8)  # Should be counted

def no_annotation(calc):
    return calc.add(9, 10)  # Should NOT be counted (unresolvable)
"""
    # Verify Calculator.add == 4 (all annotated parameters)
```

#### 3. Module-Level Variable Tests

**Purpose**: Verify module-level variables work correctly

```python
def test_module_level_variables():
    """Module-level variables should be accessible in functions."""
    code = """
class Logger:
    def log(self, msg): print(msg)

# Module-level variable
logger = Logger()

def foo():
    logger.log("from foo")  # Should use module-level logger

def bar():
    logger = Logger()  # Function-local shadows module-level
    logger.log("from bar")  # Should use function-local logger

logger.log("at module level")  # Module-level call
"""
    # Verify Logger.log == 3 (all three calls)
```

#### 4. String Annotation Tests

**Purpose**: Verify forward reference support

```python
def test_string_annotations():
    """String annotations should be resolved for forward references."""
    code = """
def process(calc: "Calculator"):  # Forward reference
    return calc.add(1, 2)

class Calculator:
    def add(self, x, y): return x + y
"""
    # Verify Calculator.add == 1
```

#### 5. Annotated Variable Tests

**Purpose**: Verify annotated assignments work

```python
def test_annotated_variables():
    """Annotated variables should enable call resolution."""
    code = """
class Calculator:
    def add(self, x, y): return x + y

def foo():
    calc: Calculator = get_calculator()  # We trust the annotation
    return calc.add(1, 2)  # Should be counted
"""
    # Verify Calculator.add == 1
```

#### 6. Limitation Tests

**Purpose**: Verify intentional limitations are handled correctly

```python
def test_nested_function_limitation():
    """Parent scope variables intentionally not resolved."""
    code = """
class Handler:
    def handle(self): pass

def outer():
    h = Handler()

    def inner():
        h.handle()  # Parent scope - should NOT be counted

    h.handle()  # Current scope - should be counted
"""
    # Verify Handler.handle == 1 (only direct scope)

def test_complex_type_limitation():
    """Complex types should be treated as unresolvable."""
    code = """
from typing import Optional, Union

def process_optional(calc: Optional[Calculator]):
    return calc.add(1, 2)  # Should NOT be counted

def process_union(calc: Union[Calculator, Processor]):
    return calc.add(3, 4)  # Should NOT be counted
"""
    # Verify Calculator.add == 0 (complex types not supported)
```

## What We Will Track vs. What We Won't

### ✅ What We Will Track (High Confidence)

**Direct instantiation**:
```python
calc = Calculator()
calc.add(1, 2)  # ✅ Counted
```

**Simple parameter annotations** (all parameter types):
```python
def foo(calc: Calculator):          # ✅ Regular parameter
def bar(calc: Calculator, /):       # ✅ Positional-only
def baz(*, calc: Calculator):       # ✅ Keyword-only
    calc.add(1, 2)  # ✅ All counted
```

**Annotated variables**:
```python
calc: Calculator = get_calculator()
calc.add(1, 2)  # ✅ Counted (we trust the annotation)
```

**Module-level variables**:
```python
logger = Logger()  # At module level
def foo():
    logger.log("msg")  # ✅ Counted
```

**String annotations (forward references)**:
```python
def process(calc: "Calculator"):  # ✅ Forward reference supported
    calc.add(1, 2)  # ✅ Counted
```

### ❌ What We Won't Track (Will Remain Unresolvable)

**Nested function parent scope variables** (Currently not implemented, marked for future reconsideration):
```python
def outer():
    h = Handler()
    def inner():
        h.handle()  # ❌ Parent scope lookup not currently implemented
```

**Unannotated parameters**:
```python
def foo(calc):  # No type annotation
    calc.add(1, 2)  # ❌ Unresolvable
```

***args and **kwargs annotations** (Intentional limitation):
```python
def foo(*args: SomeType, **kwargs: AnotherType):
    # ❌ We don't track these even if annotated
    # Would require complex access pattern analysis
```

**Complex types**:
```python
calc: Calculator | Processor  # ❌ Union type
calc: Optional[Calculator]     # ❌ Optional
calc: list[Calculator]         # ❌ Generic
```

**Return values without annotation**:
```python
calc = get_calculator()  # Don't know return type
calc.add(1, 2)  # ❌ Unresolvable
```

**Complex expressions**:
```python
calc = x if condition else y
calc = some_list[0]
calc = getattr(obj, 'calculator')
```

## Future Work

### Future Reconsideration: Nested Function Parent Scope Variables

**Current Status**: Not implemented in this phase - marked for future reconsideration
**Rationale**: May be too restrictive for real-world usage, needs further evaluation

**Analysis Needed**:
- Survey real codebases to measure how common this pattern is
- Evaluate complexity vs. benefit trade-off
- Consider if partial support (1-level parent scope) would be sufficient

**Implementation Path** (if deemed valuable):
```python
def _resolve_variable_in_parent_scopes(self, var_name: str) -> str | None:
    """Try to resolve variable in parent scopes (up to N levels)."""
    current_scope_depth = len([s for s in self._scope_stack if s.kind == ScopeKind.FUNCTION])

    # Try parent function scopes (limit to avoid complexity)
    for depth in range(1, min(current_scope_depth, 3)):  # Max 2 parent levels
        parent_scope = self._get_scope_at_depth(-depth)
        scoped_var = f"{parent_scope}.{var_name}"
        if scoped_var in self.scoped_variables:
            return self.scoped_variables[scoped_var]

    return None
```

### Class Attributes (e.g., `self.connection_pool`)

**Not included in this implementation** - requires separate tracking of class-level attributes and understanding of `self` context in methods.

**Future implementation**: Track class attribute assignments and resolve `self.attr` calls using class context.

### @dataclass Fields Support

**Not included in this implementation** - While @dataclass fields are mentioned in project_status.md as future work, they require specialized handling of field() declarations and __init__ generation.

**Future implementation**: Parse @dataclass decorators and field declarations to enable tracking of dataclass instance attributes.

### Import Aliases

**Not included in this implementation** - requires import statement processing and alias resolution.

**Future implementation**: Track `from calc import Calculator as Calc` patterns and resolve aliases to original names.

## Success Metrics

### Immediate Success Criteria

1. ✅ Instance method calls fixed: `calc.add()` correctly counted
2. ✅ No scope bleeding: Variables in different functions stay separate
3. ✅ Parameter annotations work: All parameter types enable tracking
4. ✅ Module variables work: Top-level assignments accessible in functions
5. ✅ String annotations work: Forward references are resolved
6. ✅ No regressions: All existing tests continue to pass

### Quality Metrics

- **Test Coverage**: 100% coverage maintained
- **Performance**: Minimal overhead (single AST pass)
- **Memory**: O(assignments + annotations) - reasonable for most files
- **Accuracy**: Conservative resolution prevents false positives

## Implementation Sequence

1. **Prerequisites completed** (class-detection and unresolvable-call-reporting plans)
2. **Add variable tracking infrastructure** to `CallCountVisitor`
3. **Implement parameter annotation tracking** in `visit_FunctionDef`
4. **Add assignment tracking** (`visit_Assign`, `visit_AnnAssign`)
5. **Implement type extraction helpers** using class detection improvements
6. **Update call resolution** in `_extract_call_name`
7. **Write comprehensive test suite** covering all scenarios
8. **Test with demo files** to verify bug fixes
9. **Run full test suite** to ensure no regressions

## Edge Cases and Design Decisions

### Handled Correctly

- **Variable shadowing**: Inner scope shadows outer (correct Python semantics)
- **Reassignment**: Last assignment in scope wins
- **String annotations**: Forward references supported
- **Self calls**: Continue to work via existing scope stack logic

### Conservative Choices

- **Unknown variables**: Return None (unresolvable) rather than guess
- **Complex types**: Skip rather than partially handle
- **Unannotated parameters**: Don't try to infer
- **Parent scope variables**: Not implemented in this phase (marked for future reconsideration)

## Conclusion

This implementation provides accurate, scope-aware variable tracking that fixes the instance method call counting bug while maintaining the project's philosophy of conservative, accurate analysis. By building on the existing scope infrastructure and the prerequisite class detection improvements, we achieve reliable call resolution for the most common patterns while clearly documenting limitations for edge cases.

The design is extensible and provides a solid foundation for future enhancements like import resolution and cross-module analysis, making it a strategic investment in the project's long-term capabilities.
