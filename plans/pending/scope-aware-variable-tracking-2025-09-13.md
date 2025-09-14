# Scope-Aware Variable Tracking with Type Annotations - Implementation Plan

**Date**: 2025-09-13
**Goal**: Implement accurate variable type resolution to fix method call attribution bugs while maintaining simplicity and accuracy

## Problem Context

### The Core Bug

Currently, instance method calls are not being counted correctly:

```python
# Example from demo_files/example_1.py
class Calculator:
    def add(self, a, b):
        return a + b

def foo():
    calc = Calculator()
    return calc.add(5, 7)  # This call is NOT being counted!

# Current behavior:
# - AST sees: calc.add() where calc is just a variable name
# - Parser expects: Calculator.add as the qualified name
# - Result: No match → call count = 0
```

### The Scope Problem

The original plan (now in `plans/discarded/`) had a critical flaw - no function-level scope awareness:

```python
def foo():
    calc = Calculator()  # Would store as {"calc": "Calculator"}
    calc.add(1, 2)

def bar():
    calc = 5  # Same variable name, different type!
    # The old approach would still think calc is a Calculator
```

Without scope tracking, variable type information bleeds across function boundaries, causing incorrect call attribution.

## Solution: Scope-Aware Variable Tracking

### Core Design Decision: Build Our Own Solution

After extensive research into using existing type checkers (mypy, pyright), we've decided to build our own limited solution because:

1. **Pyright**: Explicitly not designed for programmatic type extraction (maintainer confirmed)
2. **Mypy**: Unstable API that breaks frequently (SQLAlchemy deprecated their plugin for this reason)
3. **Our Limited Needs**: We only need to resolve `calc.add()` → `Calculator.add`, not full type inference
4. **Project Philosophy**: Emphasizes "conservative, accurate analysis" - we control what we trust

### Implementation Approach: Fully Qualified Scope Names

Every variable gets a unique qualified name based on its scope:
- Module-level: `__module__.variable_name`
- Function-level: `function_name.variable_name`
- Nested functions: `outer_function.inner_function.variable_name`

This ensures complete isolation between scopes while maintaining simplicity.

## Prerequisites: Data Model Updates

### Tracking Unresolvable Calls

Before implementing the variable tracking, we need infrastructure to distinguish between resolved and unresolvable calls:

**File**: `src/annotation_prioritizer/models.py`

```python
@dataclass(frozen=True)
class CallCountResult:
    """Result of call counting analysis."""
    resolved_counts: tuple[CallCount, ...]  # Successfully resolved calls
    unresolvable_count: int  # Number of calls that couldn't be resolved
    unresolvable_examples: tuple[str, ...]  # First 5 examples for debugging
```

This will require updating `count_function_calls()` to return `CallCountResult` instead of `tuple[CallCount, ...]`, and updating the analyzer and output modules accordingly.

**Updates needed in analyzer.py**:
```python
# Change line 30 from:
call_counts = count_function_calls(file_path, function_infos)
call_count_map = {cc.function_qualified_name: cc.call_count for cc in call_counts}

# To:
result = count_function_calls(file_path, function_infos)
call_count_map = {cc.function_qualified_name: cc.call_count for cc in result.resolved_counts}
```

## Detailed Implementation Steps

### Step 0: Create Failing Tests First (Prerequisite)

**File**: Add to existing `tests/unit/test_call_counter.py`

Before fixing the bug, add a test to the existing test file that demonstrates the current broken behavior:

```python
def test_instance_method_calls_bug():
    """Test that demonstrates the current bug - THIS SHOULD FAIL INITIALLY."""
    code = """
class Calculator:
    def add(self, a, b):
        return a + b

def foo():
    calc = Calculator()
    return calc.add(5, 7)  # Currently NOT counted
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            FunctionInfo(
                name="add",
                qualified_name="Calculator.add",
                parameters=(...),  # details omitted for brevity
                has_return_annotation=False,
                line_number=3,
                file_path=temp_path,
            ),
        )

        result = count_function_calls(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # This assertion SHOULD FAIL with current code (returns 0)
        # After our fix, it should PASS (returns 1)
        assert call_counts["Calculator.add"] == 1
```

### Step 1: Update CallCountVisitor Data Structures

**File**: `src/annotation_prioritizer/call_counter.py`

```python
class CallCountVisitor(ast.NodeVisitor):
    def __init__(self, call_counts: dict[str, int]) -> None:
        super().__init__()
        self.call_counts = call_counts
        self._class_stack: list[str] = []

        # NEW: Scope-aware tracking
        self.function_stack: list[str] = []  # Track function nesting
        self.scoped_variables: dict[str, str] = {}  # "scope.varname" -> "ClassName"

    def get_current_scope(self) -> str:
        """Get the fully qualified scope name."""
        if self.function_stack:
            return ".".join(self.function_stack)
        return "__module__"
```

### Step 2: Implement Scope Tracking

```python
@override
def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
    """Visit function definition to track scope and parameter types."""
    self.function_stack.append(node.name)

    # Track parameter type annotations
    for arg in node.args.args:
        if arg.annotation:
            param_type = self._extract_type_from_annotation(arg.annotation)
            if param_type:
                scope = self.get_current_scope()
                self.scoped_variables[f"{scope}.{arg.arg}"] = param_type

    self.generic_visit(node)
    self.function_stack.pop()

# Also handle async functions
visit_AsyncFunctionDef = visit_FunctionDef
```

### Step 3: Track Variable Assignments

```python
@override
def visit_Assign(self, node: ast.Assign) -> None:
    """Track variable assignments to detect type information."""
    # Handle single target assignments
    if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        var_name = node.targets[0].id
        class_name = self._extract_constructor_name(node.value)
        if class_name:
            scope = self.get_current_scope()
            self.scoped_variables[f"{scope}.{var_name}"] = class_name

    self.generic_visit(node)

@override
def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
    """Track annotated assignments like 'calc: Calculator = ...'."""
    if isinstance(node.target, ast.Name):
        var_name = node.target.id
        type_name = self._extract_type_from_annotation(node.annotation)
        if type_name:
            scope = self.get_current_scope()
            self.scoped_variables[f"{scope}.{var_name}"] = type_name

    self.generic_visit(node)
```

### Step 4: Helper Methods for Type Extraction

```python
def _extract_type_from_annotation(self, annotation: ast.expr) -> str | None:
    """Extract type name from annotation node."""
    # Handle simple name annotations: Calculator
    if isinstance(annotation, ast.Name):
        return annotation.id

    # Handle string annotations (forward references): "Calculator"
    if isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        # For simple string annotations, just return the string value
        # Complex string annotations like "Optional[Calculator]" will fail parsing
        # and be treated as unsupported (returning None)
        try:
            # Try to parse as a simple identifier
            if annotation.value.isidentifier():
                return annotation.value
        except:
            pass
        return None  # Complex string annotation

    # Handle qualified type annotations: typing.Optional (just for detection)
    if isinstance(annotation, ast.Attribute):
        # We don't support these yet, but explicitly check to document
        return None  # Unsupported: typing.Optional, etc.

    # Handle subscript annotations: Optional[Calculator], List[Calculator]
    if isinstance(annotation, ast.Subscript):
        # We don't support generics yet, but explicitly check to document
        return None  # Unsupported: generics

    # Any other annotation type we don't recognize
    return None  # Unsupported: unknown annotation type

def _extract_constructor_name(self, node: ast.expr) -> str | None:
    """Extract class name from constructor call expressions."""
    # Handle: ClassName()
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        # Check if it looks like a class (capitalized)
        name = node.func.id
        if name and name[0].isupper():
            return name

    # Handle: module.ClassName() - extract just ClassName
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        name = node.func.attr
        if name and name[0].isupper():
            return name

    return None
```

### Step 5: Enhanced Call Resolution

```python
def _extract_call_name(self, node: ast.Call) -> str | None:
    """Extract the qualified name of the called function."""
    func = node.func

    # Direct function call: function_name()
    if isinstance(func, ast.Name):
        return func.id

    # Method call: obj.method_name()
    if isinstance(func, ast.Attribute):
        # Handle self.method_name() calls (unchanged)
        if isinstance(func.value, ast.Name) and func.value.id == "self":
            if self._class_stack:
                return ".".join([*self._class_stack, func.attr])
            return func.attr

        # NEW: Handle instance method calls via variables
        if isinstance(func.value, ast.Name):
            var_name = func.value.id
            scope = self.get_current_scope()

            # Try current scope first
            scoped_var = f"{scope}.{var_name}"
            if scoped_var in self.scoped_variables:
                class_name = self.scoped_variables[scoped_var]
                return f"{class_name}.{func.attr}"

            # DESIGN DECISION: No parent scope lookup
            # We consciously choose NOT to implement parent scope traversal
            # to keep complexity low. This is a permanent limitation, not
            # a temporary one. Nested function variables from parent scopes
            # will remain unresolvable.

            # Try module scope (for module-level variables)
            module_var = f"__module__.{var_name}"
            if module_var in self.scoped_variables:
                class_name = self.scoped_variables[module_var]
                return f"{class_name}.{func.attr}"

            # Unknown variable type - might be a class name for static calls
            # Only treat as class name if capitalized
            if var_name[0].isupper():
                return f"{var_name}.{func.attr}"

            # Otherwise, we don't know the type - return None (unresolvable)
            return None

        # Handle qualified calls (unchanged)
        if isinstance(func.value, ast.Attribute):
            return func.attr

    return None
```

### Step 6: Comprehensive Test Coverage

**File**: Add these tests to existing `tests/unit/test_call_counter.py` or create new `test_call_counter_scopes.py`

```python
def test_scope_isolation():
    """Test that variable types are isolated between functions."""
    test_file = tmp_path / "test_scopes.py"
    test_file.write_text("""
class Calculator:
    def add(self, x, y): return x + y

class Processor:
    def process(self): pass

def foo():
    calc = Calculator()
    calc.add(1, 2)  # Should count for Calculator.add

def bar():
    calc = Processor()  # Same variable name, different type!
    calc.process()  # Should count for Processor.process, not Calculator
""")

    functions = parse_function_definitions(str(test_file))
    call_counts = count_function_calls(str(test_file), functions)
    count_dict = {cc.function_qualified_name: cc.call_count for cc in call_counts}

    assert count_dict["Calculator.add"] == 1
    assert count_dict["Processor.process"] == 1

def test_parameter_type_annotations():
    """Test that parameter type annotations are used."""
    test_file = tmp_path / "test_params.py"
    test_file.write_text("""
class Calculator:
    def add(self, x, y): return x + y

def process_with_annotation(calc: Calculator):
    return calc.add(5, 7)  # Should be counted!

def process_without_annotation(calc):
    return calc.add(3, 4)  # Cannot resolve - not counted
""")

    functions = parse_function_definitions(str(test_file))
    call_counts = count_function_calls(str(test_file), functions)
    count_dict = {cc.function_qualified_name: cc.call_count for cc in call_counts}

    assert count_dict["Calculator.add"] == 1  # Only the annotated parameter call

def test_module_level_variables():
    """Test that module-level variables work correctly."""
    test_file = tmp_path / "test_module_vars.py"
    test_file.write_text("""
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
""")

    functions = parse_function_definitions(str(test_file))
    call_counts = count_function_calls(str(test_file), functions)
    count_dict = {cc.function_qualified_name: cc.call_count for cc in call_counts}

    assert count_dict["Logger.log"] == 3  # All three calls

def test_nested_functions():
    """Test nested function scoping - permanent design limitation."""
    test_file = tmp_path / "test_nested.py"
    test_file.write_text("""
class Handler:
    def handle(self): pass

def outer():
    h = Handler()

    def inner():
        # PERMANENT LIMITATION: Parent scope variables not resolved
        # This is a conscious design decision to keep complexity low
        h.handle()  # Will NOT be counted (unresolvable)

    h.handle()  # This call in outer scope WILL be counted
""")

    functions = parse_function_definitions(str(test_file))
    call_counts = count_function_calls(str(test_file), functions)
    count_dict = {cc.function_qualified_name: cc.call_count for cc in call_counts}

    # Only direct scope supported (current function or module level)
    # Parent scope traversal is intentionally not implemented
    assert count_dict["Handler.handle"] == 1  # Only the outer scope call
```

## What We Will Track vs What We Won't (After Implementation)

Once this plan is implemented, here's what the tool will be capable of tracking:

### What We Will Track (High Confidence)

✅ **Direct instantiation**:
```python
calc = Calculator()
calc.add(1, 2)  # Counted
```

✅ **Simple parameter annotations**:
```python
def foo(calc: Calculator):
    calc.add(1, 2)  # Counted
```

✅ **Annotated variables**:
```python
calc: Calculator = get_calculator()
calc.add(1, 2)  # Counted (we trust the annotation)
```

✅ **Module-level variables**:
```python
logger = Logger()  # At module level
def foo():
    logger.log("msg")  # Counted
```

### What We Won't Track (Will Remain Unresolvable)

❌ **Nested function parent scope variables** (Permanent design limitation):
```python
def outer():
    h = Handler()
    def inner():
        h.handle()  # Parent scope lookup intentionally not implemented
```

❌ **Unannotated parameters**:
```python
def foo(calc):  # No type annotation
    calc.add(1, 2)  # Unresolvable
```

❌ **Complex types**:
```python
calc: Calculator | Processor  # Union type
calc: Optional[Calculator]     # Optional
calc: list[Calculator]         # Generic
```

❌ **Return values without annotation**:
```python
calc = get_calculator()  # Don't know return type
calc.add(1, 2)  # Unresolvable
```

❌ **Complex expressions**:
```python
calc = x if condition else y
calc = some_list[0]
calc = getattr(obj, 'calculator')
```

❌ **Class attributes** (Deferred to future enhancement):
```python
class Foo:
    calc = Calculator()  # Class-level attribute
    def use_it(self):
        self.calc.add()  # Won't be tracked in this implementation
```

❌ **Import aliases**:
```python
from calculators import Calculator as Calc
c = Calc()  # Won't track that Calc is Calculator
```

### Future Phases (If Needed)

**Phase 2**: Handle common patterns
- `Optional[Calculator]` → treat as Calculator
- String annotations: `"Calculator"`
- Simple return type inference

**Phase 3**: Advanced type support
- Union types with type narrowing
- Generic types
- Protocol types

## Why This Approach Over Alternatives

### Why Not Use Mypy/Pyright?

1. **Instability**: Mypy's API breaks with every release (SQLAlchemy deprecated their plugin)
2. **Overhead**: Full type checking for simple variable resolution is overkill
3. **Complexity**: We'd use 5% of capabilities while dealing with 100% of complexity
4. **Control**: We can't control what they trust/infer

### Why Not Simpler Approaches?

1. **No tracking**: Would miss all instance method calls
2. **Global dictionary**: Would have scope contamination
3. **Clear on function entry**: Would lose module-level variables

### Why This Specific Implementation?

1. **Accurate**: Complete scope isolation prevents cross-contamination
2. **Simple**: Natural extension of existing class_stack pattern
3. **Maintainable**: Clear, explicit scope prefixes make debugging easy
4. **Conservative**: Only tracks what we're confident about

## Success Metrics

### Immediate Success Criteria

1. ✅ `example_1.py` fixed: Calculator.add shows correct call count
2. ✅ No scope bleeding: Variables in different functions stay separate
3. ✅ Parameter annotations work: `foo(calc: Calculator)` enables tracking
4. ✅ Module variables work: Top-level assignments are accessible in functions
5. ✅ No regressions: All existing tests continue to pass

### Performance Expectations

- **Time**: Single AST pass, minimal overhead
- **Memory**: O(n) where n = number of assignments + annotations
- **Scalability**: Handles large files efficiently

### Performance Risks and Mitigations

1. **Dictionary Lookup Overhead**: Each method call requires dictionary lookup
   - **Impact**: O(1) average case, negligible for most files
   - **Mitigation**: Python's dict is highly optimized, no action needed

2. **Large Files with Many Variables**:
   - **Impact**: Memory usage grows with assignments
   - **Mitigation**: Acceptable trade-off for correctness; reassignments update the same key

3. **String Annotation Parsing**:
   - **Impact**: Complex string annotations like "Optional[Calculator]" could cause issues
   - **Mitigation**: Only parse simple identifiers; complex strings return None (unsupported)

## Implementation Sequence

1. **Update data models**
   - Add CallCountResult to models.py
   - Update count_function_calls return type
   - Update analyzer.py line 30-31 to use result.resolved_counts
   - Update any output module references if needed
2. **Write failing test first**
   - Add bug test to existing test_call_counter.py
   - Run test to confirm it fails with current implementation
3. **Add scope tracking infrastructure**
   - Add function_stack and scoped_variables
   - Implement get_current_scope()
4. **Implement visit_FunctionDef**
   - Track function scope entry/exit
   - Extract parameter annotations
5. **Implement assignment tracking**
   - visit_Assign for direct instantiation
   - visit_AnnAssign for annotated variables
6. **Update call resolution**
   - Modify _extract_call_name to use scoped lookups
7. **Write comprehensive tests**
   - Scope isolation tests
   - Parameter annotation tests
   - Module variable tests
8. **Test with demo files**
9. **Run full test suite with coverage**

## Edge Cases and Decisions

### Handled Correctly

- **Variable shadowing**: Inner scope shadows outer
- **Reassignment**: Last assignment in scope wins
- **String annotations**: `"Calculator"` supported
- **Self calls**: Continue to work via class_stack

### Conservative Choices

- **Unknown variables**: Return None (unresolvable) rather than guess
- **Complex types**: Skip rather than partially handle
- **Parameters without annotations**: Don't try to infer
- **Parent scope variables**: Intentionally not supported (permanent limitation)
- **Variable deletion**: `del` statements not tracked (documented limitation)

### Future Considerations

- **Cross-module imports**: Would need import resolution
- **Inheritance**: Would need MRO resolution
- **Type narrowing**: isinstance checks could refine types

## Example: Complete Scope Resolution

```python
# What we're analyzing:
class Calculator:
    def add(self, x, y): return x + y

calc_global = Calculator()  # Module level

def process_data(calc_param: Calculator):  # Parameter
    calc_local = Calculator()  # Local variable

    calc_global.add(1, 2)   # Resolves via __module__.calc_global
    calc_param.add(3, 4)    # Resolves via process_data.calc_param
    calc_local.add(5, 6)    # Resolves via process_data.calc_local

# Final scoped_variables dict:
{
    "__module__.calc_global": "Calculator",
    "process_data.calc_param": "Calculator",
    "process_data.calc_local": "Calculator"
}

# All three calls correctly attributed to Calculator.add
```

## Conclusion

This implementation provides accurate, scope-aware variable tracking that fixes the method call attribution bug while maintaining the project's philosophy of conservative, accurate analysis. By building our own focused solution rather than depending on complex type checkers, we achieve our goals with minimal complexity and maximum control.

The phased approach allows us to start with high-confidence patterns and expand only if real-world usage shows many unresolvable calls. This pragmatic strategy balances accuracy, simplicity, and maintainability - the key goals of the annotation prioritizer project.

## Appendix: Future Enhancement - Class-Level Attributes

### The Problem

Class-level attributes are a common pattern in Python but are not handled by this implementation:

```python
class DatabaseManager:
    connection_pool = ConnectionPool()  # Class attribute

    def query(self, sql):
        conn = self.connection_pool.get()  # self.connection_pool not tracked
        return conn.execute(sql)
```

Currently, `self.connection_pool.get()` would be unresolvable because we don't track that `connection_pool` is a class attribute of type `ConnectionPool`.

### Why Not Included in This Implementation

1. **Complexity**: Requires tracking class definition context separately from function context
2. **Ambiguity**: Python allows instance attributes to shadow class attributes
3. **Scope**: The current bug fix focuses on instance variables; class attributes are a separate issue

### Proposed Future Implementation

This design is **fully compatible** with future class attribute support. Here's how it could be added:

#### 1. Track Class Definition Context

```python
class CallCountVisitor(ast.NodeVisitor):
    def __init__(self, call_counts: dict[str, int]) -> None:
        # ... existing fields ...
        self.class_attributes: dict[str, str] = {}  # "ClassName.attr" -> "Type"

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.class_stack.append(node.name)

        # NEW: Process class-level assignments
        for item in node.body:
            if isinstance(item, ast.Assign):
                # Track class attribute assignments
                self._process_class_attribute(item, node.name)
            elif isinstance(item, ast.AnnAssign):
                # Track annotated class attributes
                self._process_annotated_class_attribute(item, node.name)

        self.generic_visit(node)
        self.class_stack.pop()
```

#### 2. Extend Call Resolution

```python
def _extract_call_name(self, node: ast.Call) -> str | None:
    # ... existing code ...

    # NEW: Check for self.attribute where attribute is a class attribute
    if isinstance(func.value, ast.Name) and func.value.id == "self":
        if self.class_stack:
            # First check instance variables (existing)
            # ... existing instance variable logic ...

            # NEW: Then check class attributes
            class_name = self._class_stack[-1]
            class_attr_key = f"{class_name}.{func.value.attr}"
            if class_attr_key in self.class_attributes:
                attr_type = self.class_attributes[class_attr_key]
                return f"{attr_type}.{func.attr}"
```

#### 3. Handle Inheritance

For full support, we'd also need to:
- Track base classes in class definitions
- Resolve attributes through the inheritance chain
- Handle method resolution order (MRO)

### Implementation Complexity

- **Estimated effort**: 1-2 days
- **Risk**: Medium (inheritance and shadowing edge cases)
- **Testing needs**: Comprehensive test suite for class attributes, inheritance, shadowing

### Why This Design Enables Future Enhancement

The current implementation's design choices make this enhancement straightforward:

1. **Separate tracking dictionaries**: `scoped_variables` for instance vars, future `class_attributes` for class vars
2. **Layered lookup**: Can check multiple sources in sequence without conflicts
3. **No structural changes needed**: Pure addition of new tracking, no refactoring required

This demonstrates that the current implementation is not a dead-end but rather a solid foundation for incremental improvements.
