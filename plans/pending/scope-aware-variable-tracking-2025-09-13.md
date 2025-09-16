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

**Important Note**: While this plan focuses on single-file analysis to fix the immediate bug, **directory analysis is the primary long-term goal** of this project. Single-file analysis is a temporary MVP limitation that will be replaced by directory-wide analysis as the primary interface. The scope-aware infrastructure designed here provides an excellent foundation for the upcoming directory analysis implementation.

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

## Appendix B: Import Resolution - Future Implementation Strategy

**Analysis Date**: 2025-09-14
**Compatibility Assessment**: ✅ **Fully Compatible** - The scope-aware design provides an excellent foundation for import tracking

### Overview

The scope-aware variable tracking implementation creates infrastructure that naturally extends to support import resolution without requiring architectural changes. This appendix provides detailed guidance for future maintainers implementing cross-module call tracking.

### Why This Design Enables Import Support

The current implementation's design choices make import resolution a natural extension:

1. **Extensible Data Structures**: The `scoped_variables` dictionary can evolve from storing simple names to fully qualified module paths
2. **Visitor Pattern Foundation**: Adding `visit_Import` and `visit_ImportFrom` methods fits naturally into the existing architecture
3. **Helper Method Extension Points**: `_extract_constructor_name` and `_extract_type_from_annotation` provide clear places to add import resolution logic
4. **Conservative Philosophy**: The project's emphasis on "only track what we're confident about" aligns with import resolution challenges

### High-Level Implementation Approach

#### Phase 1: Basic Import Tracking

**Goal**: Track simple import statements and resolve basic imported types

**Implementation Strategy**:
```python
class CallCountVisitor(ast.NodeVisitor):
    def __init__(self, call_counts: dict[str, int]) -> None:
        # ... existing fields ...
        self.imports: dict[str, str] = {}  # "LocalName" -> "module.path.FullName"
        self.module_aliases: dict[str, str] = {}  # "alias" -> "actual.module"

    def visit_Import(self, node: ast.Import) -> None:
        """Track 'import module' statements."""
        for alias in node.names:
            if alias.asname:
                # import calculator.Calculator as Calc
                self.module_aliases[alias.asname] = alias.name
            else:
                # import calculator
                self.module_aliases[alias.name.split('.')[-1]] = alias.name

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Track 'from module import name' statements."""
        if node.module is None:
            return  # Skip relative imports for now

        for alias in node.names:
            local_name = alias.asname if alias.asname else alias.name
            full_name = f"{node.module}.{alias.name}"
            self.imports[local_name] = full_name
```

**Data Model Evolution**:
```python
# Current storage:
scoped_variables["foo.calc"] = "Calculator"

# With import support:
scoped_variables["foo.calc"] = "mypackage.calculator.Calculator"
```

#### Phase 2: Enhanced Type Resolution

**Enhanced Constructor Detection**:
```python
def _extract_constructor_name(self, node: ast.expr) -> str | None:
    """Extract class name, now with import resolution."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
        name = node.func.id
        if name and name[0].isupper():
            # Check if it's an imported type
            if name in self.imports:
                return self.imports[name]  # Return fully qualified name
            return name  # Local class

    # Handle module.ClassName() with import aliases
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if isinstance(node.func.value, ast.Name):
            module_name = node.func.value.id
            class_name = node.func.attr
            if module_name in self.module_aliases:
                full_module = self.module_aliases[module_name]
                return f"{full_module}.{class_name}"

        # Fallback to current behavior
        name = node.func.attr
        if name and name[0].isupper():
            return name

    return None
```

### Multi-File Analysis Architecture

#### Directory Processing Strategy

**Recommended Approach**: Two-pass analysis for dependency resolution

```python
def analyze_project(project_path: Path) -> ProjectAnalysisResult:
    """Analyze entire Python project with import resolution."""

    # Pass 1: Build module map and extract all function definitions
    module_map = {}  # module_path -> {classes, functions, imports}
    all_functions = []

    for py_file in project_path.rglob("*.py"):
        module_info = extract_module_info(py_file)
        module_map[py_file] = module_info
        all_functions.extend(module_info.functions)

    # Pass 2: Analyze calls with full import context
    all_call_counts = []
    for py_file, module_info in module_map.items():
        call_counts = count_function_calls_with_imports(
            py_file, all_functions, module_info.imports
        )
        all_call_counts.extend(call_counts)

    return ProjectAnalysisResult(all_call_counts)
```

#### Import Resolution Challenges

**Challenge 1: Relative Imports**
```python
# These require package structure analysis
from .calculator import Calculator
from ..utils.math import advanced_calc
```

**Recommendation**: Start with absolute imports only. Add relative import support in a later phase after measuring real-world usage patterns.

**Challenge 2: Star Imports**
```python
from calculator import *  # Imports unknown set of names
```

**Recommendation**: Treat as unresolvable. Document this limitation clearly. Most well-structured codebases avoid star imports.

**Challenge 3: Dynamic Imports**
```python
Calculator = getattr(some_module, "Calculator")
imported_module = importlib.import_module("calculator")
```

**Recommendation**: Mark as unresolvable. These patterns are rare and would require runtime analysis to resolve properly.

### Implementation Phases and Risk Assessment

#### Phase 1: Foundation (Low Risk)
- **Scope**: Single-module imports (`from calculator import Calculator`)
- **Risk Level**: Low - natural extension of existing infrastructure
- **Estimated Effort**: 2-3 days
- **Success Criteria**: Basic import statements enable variable type resolution

#### Phase 2: Module Aliases (Medium Risk)
- **Scope**: Handle `import calculator as calc` patterns
- **Risk Level**: Medium - requires tracking module aliases separately
- **Estimated Effort**: 3-4 days
- **Success Criteria**: Aliased imports work correctly

#### Phase 3: Project-Wide Analysis (High Risk)
- **Scope**: Multi-file analysis with dependency resolution
- **Risk Level**: High - requires fundamental architecture changes
- **Estimated Effort**: 1-2 weeks
- **Success Criteria**: Entire Python packages can be analyzed

#### Phase 4: Advanced Imports (Very High Risk)
- **Scope**: Relative imports, complex package structures
- **Risk Level**: Very High - Python import semantics are complex
- **Estimated Effort**: 2-3 weeks
- **Success Criteria**: Real-world packages with complex imports work

### Data Model Changes Required

#### New Data Structures

```python
@dataclass(frozen=True)
class ImportInfo:
    """Information about an import statement."""
    local_name: str  # Name used in the importing module
    full_qualified_name: str  # Full module path
    import_type: Literal["direct", "from", "alias"]  # How it was imported

@dataclass(frozen=True)
class ModuleAnalysisResult:
    """Results of analyzing a single module."""
    file_path: Path
    imports: tuple[ImportInfo, ...]
    functions: tuple[FunctionInfo, ...]
    call_counts: tuple[CallCount, ...]
    unresolvable_calls: int

@dataclass(frozen=True)
class ProjectAnalysisResult:
    """Results of analyzing an entire project."""
    modules: tuple[ModuleAnalysisResult, ...]
    total_functions: int
    total_calls: int
    cross_module_calls: int
    unresolvable_calls: int
```

#### Backward Compatibility Strategy

**Principle**: All changes must be backward compatible with single-file analysis

```python
# Current API (must continue to work):
def count_function_calls(file_path: str, functions: tuple[FunctionInfo, ...]) -> CallCountResult:
    """Single-file analysis (existing API)."""
    # Implementation stays the same, just enhanced internally

# New API for multi-file:
def count_function_calls_project(
    project_path: Path,
    include_patterns: list[str] = ["**/*.py"]
) -> ProjectAnalysisResult:
    """Multi-file project analysis (new API)."""
```

### Testing Strategy for Import Support

#### Unit Test Categories

**Import Statement Parsing Tests**:
```python
def test_simple_from_import():
    """Test 'from module import Class' parsing."""

def test_import_with_alias():
    """Test 'import module as alias' parsing."""

def test_multiple_imports():
    """Test 'from module import Class1, Class2' parsing."""
```

**Cross-Module Resolution Tests**:
```python
def test_cross_module_method_calls():
    """Test that imported classes enable method call resolution."""
    # Create module A with Calculator class
    # Create module B that imports Calculator and uses it
    # Verify calls are counted correctly
```

**Edge Case Tests**:
```python
def test_import_name_conflicts():
    """Test handling of name conflicts between imports and local classes."""

def test_circular_imports():
    """Test handling of circular import dependencies."""
```

#### Integration Test Strategy

**Real-World Package Testing**:
- Test against well-known open-source packages
- Start with simple packages, gradually increase complexity
- Measure analysis completeness (resolved vs unresolvable calls)
- Identify common patterns that need support

### Performance Considerations

#### Memory Usage Scaling

**Current**: O(variables per file)
**With Imports**: O(variables per project + imports per project)

**Mitigation Strategy**:
- Use string interning for repeated module names
- Consider lazy loading of module information
- Profile memory usage with large projects

#### Analysis Time Complexity

**Current**: O(AST nodes per file)
**With Multi-File**: O(AST nodes per project + dependency resolution)

**Optimization Opportunities**:
- Cache parsed import information
- Parallelize file processing where possible
- Skip analysis of files that haven't changed

### Configuration and Flexibility

#### Recommended Configuration Options

```python
@dataclass(frozen=True)
class ImportAnalysisConfig:
    """Configuration for import resolution behavior."""
    resolve_relative_imports: bool = False  # Start with False
    follow_star_imports: bool = False  # Always False for now
    max_import_depth: int = 10  # Prevent infinite recursion
    ignore_patterns: tuple[str, ...] = ("test_*.py", "*_test.py")
    strict_mode: bool = True  # Fail on unresolvable imports vs skip
```

#### Fallback Behavior

**Principle**: When import resolution fails, fall back to current behavior

```python
def resolve_variable_type(var_name: str, scope: str) -> str | None:
    """Resolve variable type with import fallback."""
    # Try import-aware resolution first
    if full_type := resolve_with_imports(var_name, scope):
        return full_type

    # Fall back to current simple resolution
    return resolve_without_imports(var_name, scope)
```

### Migration Strategy

#### Incremental Implementation Path

1. **Add import tracking infrastructure** (no behavior change)
2. **Enable import resolution for single files** (enhance existing behavior)
3. **Add multi-file analysis as new API** (no existing API changes)
4. **Gradually expand import support** (relative imports, aliases, etc.)

#### Compatibility Guarantees

- Single-file analysis API remains unchanged
- All existing test cases continue to pass
- New functionality is opt-in
- Clear documentation of supported vs unsupported import patterns

### Success Metrics and Evaluation

#### Quantitative Goals

- **Coverage**: >80% of method calls in typical projects should be resolvable
- **Performance**: Multi-file analysis should complete in <30 seconds for medium projects (1000+ files)
- **Accuracy**: <5% false positive rate in call attribution

#### Qualitative Evaluation

- **Maintainability**: New code should follow existing patterns and be well-tested
- **Documentation**: Clear explanation of supported import patterns
- **Error Handling**: Graceful degradation when imports can't be resolved

### Known Limitations and Future Work

#### Permanent Limitations (By Design)

- **Dynamic imports**: `importlib.import_module()` patterns
- **Computed import names**: `from module import getattr(obj, 'name')`
- **Runtime import modification**: Monkey-patching of imported modules

#### Future Enhancement Opportunities

- **Type stub support**: Use `.pyi` files for better type resolution
- **Package.json equivalents**: Parse `pyproject.toml` for dependency information
- **IDE integration**: Export results in Language Server Protocol format

### Conclusion

The scope-aware variable tracking implementation provides an excellent foundation for import resolution. The key insight is that imports are essentially another form of variable assignment - they bind names to types, just like `calc = Calculator()` does.

By following the phased implementation approach outlined here, future maintainers can add import support incrementally while maintaining the project's core philosophy of conservative, accurate analysis. The existing infrastructure naturally extends to handle imports without requiring architectural changes, making this a low-risk, high-value enhancement path.

## Appendix C: Class Detection Improvements - Beyond Naming Conventions

**Analysis Date**: 2025-09-15
**Context**: The scope-aware variable tracking implementation uses `name[0].isupper()` heuristic for class detection in multiple places

### The Current Problem

The scope-aware variable tracking plan includes class detection logic that relies on checking if the first letter of a name is uppercase (seen in `_extract_constructor_name` and call resolution logic). This approach has significant limitations:

**Problems with uppercase heuristic:**
- **False positives**: Constants like `MAX_SIZE`, `HTTP_OK` are incorrectly identified as classes
- **False negatives**: Lowercase class names (non-PEP 8 compliant) are missed
- **Import blindness**: Doesn't understand imported classes at all
- **Context ignorance**: Treats all capitalized names the same regardless of usage

### Better Class Detection Approaches

**1. AST-based Detection (Highest Reliability)**
```python
class ClassRegistry:
    def __init__(self):
        self.defined_classes = set()
        self.imported_classes = set()

    def visit_ClassDef(self, node):
        """Track class definitions for definitive identification."""
        self.defined_classes.add(node.name)

    def visit_Import(self, node):
        """Track imported modules that might contain classes."""
        for alias in node.names:
            # Track module imports

    def visit_ImportFrom(self, node):
        """Track specific class imports."""
        if node.module:
            for alias in node.names:
                local_name = alias.asname if alias.asname else alias.name
                self.imported_classes.add(local_name)
```

**2. Built-in Type Registry**
```python
BUILTIN_TYPES = {
    # Primitive types
    'int', 'str', 'float', 'bool', 'bytes', 'bytearray',
    # Collections
    'list', 'dict', 'tuple', 'set', 'frozenset',
    # Common standard library classes
    'Exception', 'ValueError', 'TypeError', 'AttributeError',
    'Path', 'datetime', 'timedelta', 'Decimal',
    # Type hints
    'Optional', 'Union', 'List', 'Dict', 'Tuple', 'Set'
}

def is_known_type(name: str) -> bool:
    return name in BUILTIN_TYPES
```

**3. Contextual Analysis**
```python
def analyze_class_context(node, name):
    """Use context clues to identify classes."""

    # Inheritance context: class Foo(Bar) - Bar is definitely a class
    if isinstance(node.parent, ast.ClassDef):
        for base in node.parent.bases:
            if isinstance(base, ast.Name) and base.id == name:
                return "class_in_inheritance"

    # isinstance context: isinstance(obj, SomeType) - SomeType is a type
    if isinstance(node.parent, ast.Call):
        if (isinstance(node.parent.func, ast.Name) and
            node.parent.func.id == "isinstance"):
            return "type_in_isinstance"

    # Type annotation context
    if isinstance(node.parent, (ast.arg, ast.AnnAssign)):
        return "type_in_annotation"

    # Constructor pattern: SomeClass() where used like constructor
    if isinstance(node.parent, ast.Call) and node.parent.func == node:
        return "potential_constructor"

    return "unknown_context"
```

**4. Multi-Pass Analysis with Confidence Scoring**
```python
@dataclass(frozen=True)
class ClassDetectionResult:
    name: str
    confidence: float  # 0.0 to 1.0
    evidence: tuple[str, ...]  # List of evidence types

def detect_classes_multi_pass(ast_tree):
    """Multi-pass analysis with confidence scoring."""

    # Pass 1: Collect definitive evidence
    defined_classes = collect_class_definitions(ast_tree)
    imported_classes = collect_imports(ast_tree)

    # Pass 2: Contextual analysis
    contextual_evidence = analyze_usage_contexts(ast_tree)

    # Pass 3: Combine evidence with confidence scores
    results = []
    for name in all_potential_classes:
        confidence = calculate_confidence(name, {
            'defined': name in defined_classes,
            'imported': name in imported_classes,
            'builtin': name in BUILTIN_TYPES,
            'context': contextual_evidence.get(name, []),
            'naming': name[0].isupper() if name else False
        })

        results.append(ClassDetectionResult(
            name=name,
            confidence=confidence,
            evidence=get_evidence_list(name)
        ))

    return results

def calculate_confidence(name, evidence):
    """Calculate confidence score based on available evidence."""
    score = 0.0

    if evidence['defined']:
        score += 0.9  # Very high confidence for defined classes
    elif evidence['imported']:
        score += 0.8  # High confidence for imported classes
    elif evidence['builtin']:
        score += 0.9  # Very high confidence for built-ins

    # Contextual evidence
    context_boost = {
        'class_in_inheritance': 0.8,
        'type_in_isinstance': 0.7,
        'type_in_annotation': 0.6,
        'potential_constructor': 0.3
    }

    for ctx in evidence['context']:
        score += context_boost.get(ctx, 0.1)

    # Naming convention as last resort
    if evidence['naming'] and score < 0.2:
        score += 0.2  # Low confidence boost for naming

    return min(score, 1.0)  # Cap at 1.0
```

### Recommended Implementation Strategy

**Phase 1: Foundation (Immediate)**
1. Add `visit_ClassDef` tracking to build definitive class registry
2. Add `visit_Import` and `visit_ImportFrom` for import awareness
3. Create built-in type registry for common types
4. Replace current `name[0].isupper()` checks with registry lookups

**Phase 2: Context Analysis (Short-term)**
1. Add contextual analysis for inheritance, isinstance, annotations
2. Implement confidence scoring system
3. Add support for qualified names (`module.ClassName`)

**Phase 3: Advanced Patterns (Long-term)**
1. Handle import aliases (`from calc import Calculator as Calc`)
2. Support generic types (`List[Calculator]`)
3. Add cross-module class resolution

### Integration with Scope-Aware Variable Tracking

This class detection improvement **perfectly complements** the scope-aware variable tracking implementation:

**Synergistic Benefits:**
```python
# Enhanced variable tracking with better class detection
def visit_Assign(self, node: ast.Assign):
    if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
        var_name = node.targets[0].id

        # OLD: class_name = self._extract_constructor_name(node.value)
        # NEW: Use improved class detection
        class_detection = self.detect_constructor_class(node.value)
        if class_detection.confidence > 0.7:  # High confidence threshold
            scope = self.get_current_scope()
            self.scoped_variables[f"{scope}.{var_name}"] = class_detection.name
```

**Enhanced Type Resolution:**
```python
def _extract_type_from_annotation(self, annotation: ast.expr) -> str | None:
    if isinstance(annotation, ast.Name):
        name = annotation.id

        # Check against class registry instead of just accepting any name
        if self.is_known_class(name):
            return name

    # ... rest of annotation handling
```

### Performance Impact

**Memory**: Minimal increase (O(classes + imports) vs current O(1))
**Runtime**: Negligible - registry lookups are O(1) average case
**Accuracy**: Significant improvement in class detection precision

### Backward Compatibility

This enhancement maintains full backward compatibility:
- All existing detection continues to work
- New detection is purely additive
- Confidence scoring allows gradual migration
- Fallback to naming conventions when other methods fail

### Testing Strategy

**Unit Tests for Each Detection Method:**
```python
def test_class_definition_detection():
    """Test detection of classes defined in the same file."""

def test_import_detection():
    """Test detection of imported classes."""

def test_builtin_type_detection():
    """Test detection of built-in Python types."""

def test_contextual_detection():
    """Test context-based class identification."""

def test_confidence_scoring():
    """Test that confidence scores are calculated correctly."""
```

**Integration Tests:**
```python
def test_reduced_false_positives():
    """Verify that constants like MAX_SIZE aren't detected as classes."""

def test_improved_import_handling():
    """Verify that imported classes are properly detected."""
```

### Implementation Priority

This class detection improvement should be implemented **during** the scope-aware variable tracking implementation, not after. Since the scope-aware plan already includes `name[0].isupper()` checks in multiple places (`_extract_constructor_name`, call resolution logic), it's more efficient to implement better class detection from the start rather than building on a flawed foundation.

**Recommended Approach**: Integrate Phase 1 class detection improvements directly into the scope-aware implementation:
- Replace planned `name[0].isupper()` checks with proper class registries
- Add `visit_ClassDef` and import tracking alongside the scope tracking infrastructure
- Implement built-in type registry as part of the initial class detection logic

**Estimated Effort**: +1 day to the scope-aware implementation (vs 2-3 days if done separately)
**Risk Level**: Low - prevents building on flawed foundation
**Impact**: High - avoids implementing incorrect logic that would need immediate replacement
