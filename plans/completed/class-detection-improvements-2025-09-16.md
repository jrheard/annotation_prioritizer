# Class Detection Improvements Implementation Plan

**Created:** 2025-09-16
**Status:** COMPLETED - Class detection fully implemented
**Priority:** CRITICAL - Foundation for future improvements
**Estimated Effort:** Originally 3-4 hours, actual implementation complete

## Implementation Summary

✅ **Class Detection Completed**: The class detection system has been fully implemented with AST-based identification, eliminating false positives and providing accurate class detection.

### Key Achievements:
- **Zero False Positives**: Constants like `MAX_SIZE` no longer treated as classes
- **Complete Class Coverage**: All class patterns including nested classes and function-local classes
- **100% Test Coverage**: Comprehensive unit and integration tests added
- **Type Safety**: Uses QualifiedName type for compile-time safety
- **New Module Created**: `class_discovery.py` with ClassRegistry and ClassDiscoveryVisitor
- **Nested Class Support**: Full support for Outer.Inner.method() patterns

### Implementation Details:
- **ClassRegistry**: Simple registry tracking only user-defined classes (no builtin tracking)
- **QualifiedName Type**: All qualified names use the new type-safe QualifiedName type
- **Conservative Approach**: Only tracks classes defined in the current file
- **No Import Support**: Imported classes intentionally not tracked (future work)

## Executive Summary

Replace the current naive class detection heuristic (`name[0].isupper()`) with definitive AST-based class identification. This foundational improvement is required before implementing variable tracking or unresolvable call reporting. The new system uses a simple registry approach to definitively identify classes from AST `ClassDef` nodes only (builtin tracking was removed as unnecessary).

## Problem Statement

### Current Broken Behavior

The call counter currently treats ANY identifier before a dot as a potential class in `_extract_call_name()`:

```python
# Lines 176-179 in call_counter.py
if isinstance(func.value, ast.Name):
    class_name = func.value.id
    # TODO: is this right? why is `class_name` guaranteed to live directly on `__module__`?
    return f"__module__.{class_name}.{func.attr}"
```

This naive approach causes serious issues:

**False Positives (Main Problem):**
```python
MAX_SIZE = 100
result = MAX_SIZE.bit_length()  # Wrongly treated as __module__.MAX_SIZE.bit_length

DEFAULT_CONFIG = {"key": "value"}
value = DEFAULT_CONFIG.get("key")  # Wrongly treated as __module__.DEFAULT_CONFIG.get
```

**Note:** Non-PEP8 class names like `xmlParser` and `dataProcessor` ARE currently recognized correctly. The issue is that we treat ALL identifiers as classes, not that we miss certain class naming patterns.

**Critical Bug - Instance Method Calls:**
```python
class Calculator:
    def add(self, a, b): ...

def process():
    calc = Calculator()  # Variable assignment - not tracked
    return calc.add(5, 7)  # calc.add NOT counted - treated as __module__.calc.add
```

The fundamental problem is we have no way to distinguish between:
- Actual class names (`Calculator.add()`)
- Constants/variables (`MAX_SIZE.bit_length()`)
- Instance variables (`calc.add()`)

## Solution Design

### Core Concept: ClassRegistry

A simple, immutable registry that definitively identifies user-defined classes:

```python
@dataclass(frozen=True)
class ClassRegistry:
    """Registry of user-defined classes found in the analyzed code.

    Only tracks classes defined in the AST (via ClassDef nodes).
    Does not track Python builtins since we never analyze their methods.
    """
    classes: frozenset[QualifiedName]  # Qualified names like "__module__.Calculator"

    def is_class(self, name: QualifiedName) -> bool:
        """Check if a name is a known user-defined class."""
        return name in self.classes

    def merge(self, other: "ClassRegistry") -> "ClassRegistry":
        """Merge with another registry (for future multi-file analysis)."""
        return ClassRegistry(classes=self.classes | other.classes)
```

**Note on Builtin Types**: The implementation intentionally does not track Python builtin types (int, str, list, etc.) because:
1. We never count calls to builtin methods (they're not in `known_functions`)
2. Builtin methods are not part of the user's code that needs type annotations
3. Removing builtin tracking simplifies the implementation significantly
4. It eliminates the need to handle the special case of builtins not having `__module__` prefixes

### AST Visitor for Class Discovery

```python
class ClassDiscoveryVisitor(ast.NodeVisitor):
    """Discovers all class definitions in an AST.

    Builds a registry of class names with their scope context.
    Handles nested classes correctly using the scope stack.
    """

    def __init__(self) -> None:
        super().__init__()
        self.class_names: list[QualifiedName] = []
        self._scope_stack: ScopeStack = create_initial_stack()

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Record class definition with full qualified name."""
        # Build qualified name from current scope
        scope_names = [scope.name for scope in self._scope_stack]
        qualified_name = make_qualified_name(".".join([*scope_names, node.name]))
        self.class_names.append(qualified_name)

        # Push class scope and continue traversal for nested classes
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.CLASS, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Track function scope for nested classes inside functions."""
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.FUNCTION, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Track async function scope for nested classes."""
        self._scope_stack = add_scope(self._scope_stack, Scope(kind=ScopeKind.FUNCTION, name=node.name))
        self.generic_visit(node)
        self._scope_stack = drop_last_scope(self._scope_stack)
```

### Registry Builder Function

```python
def build_class_registry(tree: ast.AST) -> ClassRegistry:
    """Build a registry of all user-defined classes from an AST.

    Args:
        tree: Parsed AST of Python source code

    Returns:
        Immutable ClassRegistry with all discovered classes
    """
    visitor = ClassDiscoveryVisitor()
    visitor.visit(tree)

    return ClassRegistry(classes=frozenset(visitor.class_names))
```

## Import Handling - Current Limitations

### What We're NOT Handling

This implementation focuses exclusively on classes defined within the analyzed file. We explicitly do NOT handle:

1. **Standard Library Imports**
   ```python
   import math
   import json
   from collections import defaultdict
   from pathlib import Path

   # These class method calls will NOT be recognized:
   math.sqrt(16)
   json.loads("{}")
   defaultdict.fromkeys([1, 2])
   Path.home()
   ```

2. **Type Annotation Imports**
   ```python
   from typing import List, Dict, Optional

   # These are commonly used as classes but won't be recognized:
   List.copy([])
   Dict.fromkeys(["a", "b"])
   ```

3. **Third-Party Package Classes**
   ```python
   import pandas as pd
   import numpy as np
   from requests import Session

   # None of these will be recognized:
   pd.DataFrame.from_dict({})
   np.array.reshape(arr, (2, 3))
   Session.get("http://example.com")
   ```

### Why This Matters

In real-world Python code, a significant portion of "class method" calls are on imported classes:
- DataFrame operations in data science code
- Path manipulations in file handling code
- Type constructors in typed Python code

**This means our initial implementation will have limited effectiveness on codebases that heavily use imports.**

### Our Temporary Solution

When encountering `SomeName.method()` where `SomeName` isn't in our class registry:
1. We return `None` from `_extract_call_name()`
2. The call is silently ignored (not counted)
3. No error is raised or logged

This conservative approach ensures:
- No false positives (incorrectly counting non-class method calls)
- Clean upgrade path (when we add import support, more calls will simply start being counted)
- Clear scope boundaries (we only claim to handle what we can actually handle)

### What This Means for Testing

The tool will work best on:
- Self-contained modules with minimal imports
- Code that defines its own classes rather than using library classes
- Files where the primary logic is in local classes

The tool will have limited value for:
- Scripts that primarily orchestrate library calls
- Data science notebooks full of pandas/numpy operations
- Thin wrappers around third-party APIs

### Future Implementation Path

When we implement import resolution (planned for after variable tracking), we'll need to:
1. Parse import statements to build an import registry
2. Attempt to resolve imported names to their modules
3. Potentially analyze imported modules to find their class definitions
4. Handle aliased imports (`import pandas as pd`)
5. Deal with star imports (`from module import *`)

For now, we're keeping the implementation simple and focused on accurate local class detection.

### Why Builtins Are Not Tracked

Python builtin types (int, str, list, etc.) are intentionally NOT tracked because:
- We never count calls to builtin methods (they're not in `known_functions`)
- Builtin methods don't need type annotations (they're already typed in typeshed)
- Tracking them adds complexity without providing value
- It would complicate the type system (builtins don't have `__module__` prefixes)

## Integration Points

### 1. Update call_counter.py

The `CallCountVisitor` needs to accept and use a `ClassRegistry` with a new resolver method:

```python
class CallCountVisitor(ast.NodeVisitor):
    def __init__(self, known_functions: tuple[FunctionInfo, ...], class_registry: ClassRegistry) -> None:
        super().__init__()
        self.call_counts: dict[QualifiedName, int] = {
            func.qualified_name: 0 for func in known_functions
        }
        self._class_registry = class_registry
        self._scope_stack = create_initial_stack()

    def _resolve_class_name(self, class_name: str) -> QualifiedName | None:
        """Resolve a class name to its qualified form based on current scope.

        Only resolves user-defined classes found in the AST.

        Args:
            class_name: The name to resolve (e.g., "Calculator", "Outer.Inner")

        Returns:
            Qualified class name if found in registry, None otherwise
        """
        candidates = generate_name_candidates(self._scope_stack, class_name)
        return find_first_match(candidates, self._class_registry.classes)

    def _resolve_call_name(self, node: ast.Call) -> QualifiedName | None:
        """Resolve the qualified name of the called function."""
        func = node.func

        # Direct calls to functions: function_name()
        if isinstance(func, ast.Name):
            return self._resolve_function_call(func.id)

        # Method calls: obj.method_name()
        if isinstance(func, ast.Attribute):
            return self._resolve_method_call(func)

        # Dynamic calls cannot be resolved statically
        return None
```

Update the main entry point:

```python
def count_function_calls(file_path: str, known_functions: tuple[FunctionInfo, ...]) -> tuple[CallCount, ...]:
    """Count calls to known functions within the same file using AST parsing."""
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        return ()

    try:
        source_code = file_path_obj.read_text(encoding="utf-8")
        tree = ast.parse(source_code, filename=file_path)
    except (OSError, SyntaxError):
        return ()

    # NEW: Build class registry first
    class_registry = build_class_registry(tree)

    # Pass registry to visitor
    visitor = CallCountVisitor(known_functions, class_registry)
    visitor.visit(tree)

    return tuple(
        CallCount(function_qualified_name=name, call_count=count)
        for name, count in visitor.call_counts.items()
    )
```

### 2. Support String Annotations

For handling forward references and string annotations:

```python
def extract_class_from_annotation(annotation: ast.AST) -> str | None:
    """Extract class name from a type annotation.

    Handles both direct Name nodes and Constant string annotations.
    Returns the class name if found, None otherwise.

    Examples:
        Calculator -> "Calculator"
        "Calculator" -> "Calculator"
        Optional[Calculator] -> None (too complex)
    """
    if isinstance(annotation, ast.Name):
        return annotation.id
    elif isinstance(annotation, ast.Constant) and isinstance(annotation.value, str):
        # String annotation like "Calculator"
        # Simple extraction - just the string value
        # Don't try to parse complex types
        if "[" not in annotation.value and "|" not in annotation.value:
            return annotation.value
    return None
```

### 3. Two-Pass Analysis Support

The system already does two passes for forward references. Leverage this:

```python
# In analyzer.py or wherever the main analysis happens
def analyze_file(file_path: str) -> ...:
    """Main analysis with two-pass support."""

    # First pass: Parse and build registries
    tree = ast.parse(source_code)
    class_registry = build_class_registry(tree)
    function_infos = parse_function_definitions(file_path)

    # Second pass: Count calls with full context
    call_counts = count_function_calls_with_registry(
        file_path, function_infos, class_registry
    )

    # ... rest of analysis ...
```

## Testing Strategy

### Unit Tests

1. **Test ClassRegistry**
```python
def test_class_registry_identifies_ast_classes():
    registry = ClassRegistry(
        classes=frozenset([
            make_qualified_name("__module__.Calculator"),
            make_qualified_name("__module__.Parser")
        ])
    )
    assert registry.is_class(make_qualified_name("__module__.Calculator")) is True
    assert registry.is_class(make_qualified_name("__module__.Parser")) is True
    assert registry.is_class(make_qualified_name("__module__.MAX_SIZE")) is False

def test_class_registry_merge():
    registry1 = ClassRegistry(
        classes=frozenset([make_qualified_name("__module__.ClassA")])
    )
    registry2 = ClassRegistry(
        classes=frozenset([make_qualified_name("__module__.ClassB")])
    )
    merged = registry1.merge(registry2)
    assert merged.is_class(make_qualified_name("__module__.ClassA")) is True
    assert merged.is_class(make_qualified_name("__module__.ClassB")) is True
```

2. **Test Class Discovery**
```python
@pytest.mark.parametrize("source_code,expected_classes", [
    # Simple class
    ("""
class Calculator:
    pass
""", ["__module__.Calculator"]),

    # Nested class
    ("""
class Outer:
    class Inner:
        pass
""", ["__module__.Outer", "__module__.Outer.Inner"]),

    # Non-PEP8 names
    ("""
class xmlParser:
    pass
class dataProcessor:
    pass
""", ["__module__.xmlParser", "__module__.dataProcessor"]),

    # Class in function (edge case)
    ("""
def factory():
    class LocalClass:
        pass
    return LocalClass
""", ["__module__.factory.LocalClass"]),
])
def test_class_discovery_visitor(source_code, expected_classes):
    tree = ast.parse(source_code)
    registry = build_class_registry(tree)
    for class_name in expected_classes:
        assert class_name in registry.ast_classes
```

3. **Test False Positive Elimination**
```python
def test_constants_not_treated_as_classes():
    source = """
MAX_SIZE = 100
DEFAULT_CONFIG = {}
PI = 3.14

class RealClass:
    pass

def use_constants():
    MAX_SIZE.bit_length()  # Should NOT be counted as class method
    DEFAULT_CONFIG.get("key")  # Should NOT be counted
    RealClass.method()  # Would be counted if method existed
"""
    tree = ast.parse(source)
    registry = build_class_registry(tree)

    # Constants are not in the registry
    assert registry.is_class(make_qualified_name("__module__.MAX_SIZE")) is False
    assert registry.is_class(make_qualified_name("__module__.DEFAULT_CONFIG")) is False
    assert registry.is_class(make_qualified_name("__module__.PI")) is False
    # Only the actual class is in the registry
    assert registry.is_class(make_qualified_name("__module__.RealClass")) is True
```

3. **Test Imported Classes Not Counted**
```python
def test_imported_classes_not_counted():
    """Verify that imported classes are not recognized (temporary behavior)."""
    source = """
from typing import List
from collections import defaultdict
import math

def use_imports():
    List.append([], "item")  # Should NOT be counted
    defaultdict.fromkeys([1, 2])  # Should NOT be counted
    math.sqrt(16)  # Should NOT be counted
    int.from_bytes(b"test", "big")  # Should be counted (built-in)
"""
    tree = ast.parse(source)
    registry = build_class_registry(tree)

    # Imported classes not in registry
    assert not registry.is_class("List")
    assert not registry.is_class("__module__.List")
    assert not registry.is_class("defaultdict")
    assert not registry.is_class("math")

    # Built-in is recognized
    assert registry.is_class("int")
```

### Integration Tests

1. **Test End-to-End with New Registry**
```python
def test_class_method_calls_with_registry():
    test_file = write_temp_file("""
class Calculator:
    def add(self, a, b):
        return a + b

class Processor:
    def process(self, data):
        return data

def main():
    Calculator.add(None, 1, 2)  # Should count
    Processor.process(None, "data")  # Should count
    UnknownClass.method()  # Should NOT count
    CONSTANT.method()  # Should NOT count
""")

    functions = parse_function_definitions(test_file)
    counts = count_function_calls(test_file, functions)

    calc_add = next(c for c in counts if "Calculator.add" in c.function_qualified_name)
    proc_process = next(c for c in counts if "Processor.process" in c.function_qualified_name)

    assert calc_add.call_count == 1
    assert proc_process.call_count == 1
```

2. **Test Nested Classes**
```python
def test_nested_class_method_calls():
    """Test that nested class method calls are correctly resolved."""
    test_file = write_temp_file("""
class Outer:
    class Inner:
        def process(self):
            return "processing"

    def use_inner(self):
        # Should resolve to __module__.Outer.Inner.process
        Inner.process(None)

def use_at_module():
    # Won't be counted - Inner not accessible at module level
    Inner.process(None)
    # This will be counted
    Outer.Inner.process(None)
""")

    functions = parse_function_definitions(test_file)
    counts = count_function_calls(test_file, functions)

    inner_process = next(
        c for c in counts
        if c.function_qualified_name == "__module__.Outer.Inner.process"
    )
    assert inner_process.call_count == 2  # Once from use_inner, once from use_at_module
```

3. **Test Forward References**
```python
def test_forward_reference_handling():
    test_file = write_temp_file("""
def process(calc: "Calculator"):  # Forward reference
    return calc.add(1, 2)  # Won't work until variable tracking

class Calculator:
    def add(self, a, b):
        return a + b
""")

    tree = ast.parse(read_file(test_file))
    registry = build_class_registry(tree)

    # Calculator should be in registry even though used before defined
    assert registry.is_class("__module__.Calculator") is True
```

## Implementation Steps

1. **Add ClassRegistry to models.py** (30 min)
   - Define `ClassRegistry` dataclass
   - Add `PYTHON_BUILTIN_TYPES` constant
   - Add helper functions

2. **Create ClassDiscoveryVisitor** (45 min)
   - Implement in call_counter.py or new module
   - Handle nested classes and scopes
   - Build qualified names correctly

3. **Update CallCountVisitor** (1 hour)
   - Accept ClassRegistry parameter (BREAKING CHANGE - intentional)
   - Add `_resolve_class_name()` method
   - Update `_extract_call_name()` to use resolver
   - Remove naive heuristics

   **NOTE**: This is an intentional breaking API change. All existing instantiations of `CallCountVisitor` will need to be updated to pass the `class_registry` parameter. This is acceptable as it forces proper class detection throughout the codebase.

4. **Update count_function_calls()** (30 min)
   - Build registry from AST
   - Pass to visitor

5. **Fix all existing tests** (45 min)
   - Update ALL test files that instantiate `CallCountVisitor` - this is a breaking change
   - Files that MUST be updated:
     - `tests/unit/test_call_counter.py` - Multiple test functions create CallCountVisitor directly
     - `tests/integration/test_end_to_end.py` - May need updates if it directly uses call_counter
   - Every CallCountVisitor instantiation must be updated to:
     ```python
     # Build registry first
     tree = ast.parse(source_code)
     class_registry = build_class_registry(tree)
     # Then pass to visitor
     visitor = CallCountVisitor(known_functions, class_registry)
     ```
   - This breaking change is intentional and ensures consistent class detection

6. **Write comprehensive new tests** (1 hour)
   - Unit tests for ClassRegistry
   - Unit tests for ClassDiscoveryVisitor
   - Test for `_resolve_class_name()` method
   - Integration tests for call counting
   - Test for imported classes behavior
   - Edge case coverage

7. **Update documentation** (15 min)
   - Update docstrings
   - Update project_status.md

## Success Criteria (ALL MET)

1. **✅ No False Positives**: Constants like `MAX_SIZE` are never treated as classes
2. **✅ No False Negatives**: Non-PEP8 class names like `xmlParser` are correctly identified
3. **✅ Nested Classes**: Correctly handle `Outer.Inner` patterns
4. **✅ 100% Test Coverage**: All new code has tests
5. **✅ Type Safety**: Uses QualifiedName type throughout
6. **✅ Simple Design**: No unnecessary complexity from tracking builtins

## Future Considerations

### What This Enables

1. **Variable Tracking** (Step 3): With accurate class detection, we can track `calc = Calculator()` assignments
2. **Better Error Reporting**: Can distinguish "not a class" from "unknown class"
3. **Import Resolution**: Foundation for tracking imported classes

### What We're NOT Doing Yet

1. **@property Support**: Properties look like attributes but are methods. Consider adding later.
2. **@dataclass Fields**: Typed fields in dataclasses could be tracked. Future enhancement.
3. **Type Alias Support**: `TypeAlias = List[str]` - too complex for now
4. **Generic Classes**: `class Container[T]` - beyond current scope

## Risk Mitigation

1. **Performance**: Building registry adds minimal overhead (one extra AST traversal)
2. **Compatibility**: Changes are backward compatible - just more accurate
3. **Complexity**: Simple set membership check - no complex logic

## Code Location

- `src/annotation_prioritizer/models.py`: Add ClassRegistry and PYTHON_BUILTIN_TYPES
- `src/annotation_prioritizer/call_counter.py`: Update CallCountVisitor and add ClassDiscoveryVisitor
- `tests/unit/test_class_registry.py`: New test file for registry tests
- `tests/integration/test_class_detection.py`: Integration tests for full flow

## Dependencies on Other Work

- **Depends On**: Completed scope infrastructure (✅ DONE)
- **Blocks**: Unresolvable call reporting (can't report what we can't identify)
- **Blocks**: Variable tracking (need to know what's a class to track instantiations)

## Notes for Implementation

1. Start with the simplest approach - just a set of names
2. Don't over-engineer for future multi-file support yet
3. Keep the registry immutable for functional style
4. Use existing Scope infrastructure - don't reinvent
5. Conservative approach: When in doubt, return False for `is_class()`

## Commit Breakdown

This work will be implemented in 6 logical commits that build on each other:

### Commit 1: feat: add ClassRegistry data structure and Python builtin types
- Add `ClassRegistry` dataclass to `models.py`
- Implement `PYTHON_BUILTIN_TYPES` constant using `builtins` module
- Add `is_class()` and `merge()` methods
- Write unit tests for ClassRegistry

### Commit 2: feat: implement ClassDiscoveryVisitor for AST class detection
- Add `ClassDiscoveryVisitor` class (either in `call_counter.py` or new module)
- Implement `build_class_registry()` function
- Handle nested classes and scope tracking
- Write unit tests for class discovery

### Commit 3: refactor: integrate ClassRegistry into CallCountVisitor (breaking change)
- Update `CallCountVisitor.__init__()` to require `class_registry` parameter
- Add `_resolve_class_name()` method
- Update `_extract_call_name()` to use registry instead of heuristics
- **Fix ALL existing tests** that instantiate `CallCountVisitor` directly
- This is an intentional breaking API change to force proper class detection

### Commit 4: feat: wire up class registry in count_function_calls entry point
- Update `count_function_calls()` to build registry from AST
- Pass registry to `CallCountVisitor`
- Complete the end-to-end integration

### Commit 5: test: add comprehensive tests for class detection feature
- Integration tests for false positive elimination
- Tests for nested classes and forward references
- Tests verifying imported classes are not counted
- Edge case coverage

### Commit 6: docs: update documentation for class detection improvements
- Update docstrings on new/modified functions
- Update `project_status.md`
- Move plan from `pending/` to `completed/`

Each commit is individually testable and maintains a working test suite. Commit 3 is particularly critical as it's a breaking change that requires updating all existing test files.

---

**Next Steps After This:**
1. Implement unresolvable call reporting (requires knowing what's a class)
2. Then implement variable tracking (requires both class detection and unresolvable reporting)
