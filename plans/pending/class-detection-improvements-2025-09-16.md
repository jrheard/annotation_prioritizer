# Class Detection Improvements Implementation Plan

**Created:** 2025-09-16
**Status:** Pending Implementation
**Priority:** CRITICAL - Must be completed FIRST before other improvements
**Estimated Effort:** 3-4 hours

## Executive Summary

Replace the current naive class detection heuristic (`name[0].isupper()`) with definitive AST-based class identification. This foundational improvement is required before implementing variable tracking or unresolvable call reporting. The new system will use a simple registry approach to definitively identify classes from AST `ClassDef` nodes and Python built-in types.

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

A simple, immutable registry that definitively identifies classes:

```python
@dataclass(frozen=True)
class ClassRegistry:
    """Immutable registry of known classes in the analyzed code.

    Provides definitive class identification without heuristics or guessing.
    Classes are identified from two sources:
    1. AST ClassDef nodes found during parsing
    2. Python built-in types (int, str, list, etc.)
    """
    ast_classes: frozenset[str]  # Classes found via ClassDef nodes
    builtin_classes: frozenset[str]  # Python built-in type names

    def is_class(self, name: str) -> bool:
        """Check if a name is definitively known to be a class.

        Returns True only for names we're certain are classes.
        Conservative approach: False for unknowns rather than guessing.
        """
        return name in self.ast_classes or name in self.builtin_classes

    def merge(self, other: "ClassRegistry") -> "ClassRegistry":
        """Merge with another registry (for multi-file analysis future)."""
        return ClassRegistry(
            ast_classes=self.ast_classes | other.ast_classes,
            builtin_classes=self.builtin_classes  # Built-ins never change
        )
```

### Built-in Types Registry

```python
# In models.py or a new class_registry.py module
PYTHON_BUILTIN_TYPES: frozenset[str] = frozenset({
    # Fundamental types
    "int", "float", "complex", "bool", "str", "bytes", "bytearray", "memoryview",

    # Collections
    "list", "tuple", "dict", "set", "frozenset", "range",

    # Base types
    "object", "type", "super",

    # Common exception base classes
    "Exception", "BaseException", "StopIteration", "GeneratorExit",
    "KeyboardInterrupt", "SystemExit",

    # Other common built-ins that are classes
    "property", "staticmethod", "classmethod",
    "enumerate", "filter", "map", "zip", "reversed",

    # Type-related (for annotations)
    "type", "None", "NotImplemented", "Ellipsis",
})
```

### AST Visitor for Class Discovery

```python
class ClassDiscoveryVisitor(ast.NodeVisitor):
    """Discovers all class definitions in an AST.

    Builds a registry of class names with their scope context.
    Handles nested classes correctly using the scope stack.
    """

    def __init__(self) -> None:
        super().__init__()
        self.class_names: list[str] = []
        self._scope_stack: list[Scope] = [Scope(kind=ScopeKind.MODULE, name="__module__")]

    @override
    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Record class definition with full qualified name."""
        # Build qualified name from current scope
        scope_names = [scope.name for scope in self._scope_stack]
        qualified_name = ".".join([*scope_names, node.name])
        self.class_names.append(qualified_name)

        # Push class scope and continue traversal for nested classes
        self._scope_stack.append(Scope(kind=ScopeKind.CLASS, name=node.name))
        self.generic_visit(node)
        self._scope_stack.pop()

    @override
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Track function scope for nested classes inside functions."""
        self._scope_stack.append(Scope(kind=ScopeKind.FUNCTION, name=node.name))
        self.generic_visit(node)
        self._scope_stack.pop()

    @override
    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Track async function scope for nested classes."""
        self._scope_stack.append(Scope(kind=ScopeKind.FUNCTION, name=node.name))
        self.generic_visit(node)
        self._scope_stack.pop()
```

### Registry Builder Function

```python
def build_class_registry(tree: ast.AST) -> ClassRegistry:
    """Build a complete class registry from an AST.

    Pure function that discovers all class definitions in the AST
    and combines them with Python built-in types.

    Args:
        tree: Parsed AST of Python source code

    Returns:
        Immutable ClassRegistry with all discovered classes
    """
    visitor = ClassDiscoveryVisitor()
    visitor.visit(tree)

    return ClassRegistry(
        ast_classes=frozenset(visitor.class_names),
        builtin_classes=PYTHON_BUILTIN_TYPES
    )
```

## Import Handling - Current Limitations and Future Path

### What We're NOT Handling (Yet)

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

### Adding to PYTHON_BUILTIN_TYPES

We include Python built-in types in our registry because:
- They're always available without imports
- They're frequently used (`str.format()`, `dict.fromkeys()`, etc.)
- They have well-known, stable APIs
- No ambiguity about what they refer to

The `PYTHON_BUILTIN_TYPES` set provides value immediately without the complexity of import resolution.

## Integration Points

### 1. Update call_counter.py

The `CallCountVisitor` needs to accept and use a `ClassRegistry` with a new resolver method:

```python
class CallCountVisitor(ast.NodeVisitor):
    def __init__(self, known_functions: tuple[FunctionInfo, ...], class_registry: ClassRegistry) -> None:
        super().__init__()
        self.call_counts: dict[str, int] = {func.qualified_name: 0 for func in known_functions}
        self.class_registry = class_registry  # NEW
        self._scope_stack: list[Scope] = [Scope(kind=ScopeKind.MODULE, name="__module__")]

    def _resolve_class_name(self, class_name: str) -> str | None:
        """Resolve a class name to its qualified form based on current scope.

        Checks from most specific (nested class) to least specific (module) scope.
        This handles cases like:
        - Inner.method() inside Outer class -> __module__.Outer.Inner
        - Calculator.add() at module level -> __module__.Calculator

        NOTE: Currently only resolves classes defined in the current file and Python
        built-in types. Imported classes (from typing, collections, third-party packages)
        are not recognized and their method calls won't be counted.

        Args:
            class_name: The local name to resolve (e.g., "Calculator", "Inner")

        Returns:
            Qualified class name if found in registry, None otherwise

        Examples:
            "Calculator" -> "__module__.Calculator" (if defined in file)
            "int" -> "int" (built-in type)
            "List" -> None (imported from typing, not yet supported)
            "defaultdict" -> None (imported from collections, not yet supported)
        """
        candidates: list[str] = []

        # Build candidates from current scope outward
        # If we're in Outer.method(), seeing "Inner" should check:
        # 1. __module__.Outer.Inner (sibling class)
        # 2. __module__.Inner (module-level class)

        for i in range(len(self._scope_stack)):
            if self._scope_stack[i].kind == ScopeKind.CLASS:
                # Try as sibling class in this class's scope
                scope_names = [s.name for s in self._scope_stack[:i+1]]
                candidates.append(".".join([*scope_names, class_name]))

        # Always try module level as fallback
        candidates.append(f"__module__.{class_name}")

        # Check built-in types directly (they don't have __module__ prefix)
        if class_name in self.class_registry.builtin_classes:
            return class_name

        # Return first match found in AST classes registry
        for candidate in candidates:
            if candidate in self.class_registry.ast_classes:
                return candidate

        return None

    def _extract_call_name(self, node: ast.Call) -> str | None:
        """Extract the qualified name of the called function."""
        func = node.func

        # ... existing code for direct calls ...

        # Method calls: obj.method_name()
        if isinstance(func, ast.Attribute):
            # ... existing self.method() handling ...

            # Static/class method calls: ClassName.method_name()
            if isinstance(func.value, ast.Name):
                potential_class = func.value.id

                # NEW: Use resolver to check all possible scopes
                resolved_class = self._resolve_class_name(potential_class)
                if resolved_class:
                    return f"{resolved_class}.{func.attr}"

                # Not a class - might be a variable (future work)
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
        ast_classes=frozenset(["__module__.Calculator", "__module__.Parser"]),
        builtin_classes=frozenset(["int", "str"])
    )
    assert registry.is_class("__module__.Calculator") is True
    assert registry.is_class("int") is True
    assert registry.is_class("MAX_SIZE") is False
    assert registry.is_class("unknown") is False

def test_class_registry_merge():
    registry1 = ClassRegistry(
        ast_classes=frozenset(["__module__.ClassA"]),
        builtin_classes=PYTHON_BUILTIN_TYPES
    )
    registry2 = ClassRegistry(
        ast_classes=frozenset(["__module__.ClassB"]),
        builtin_classes=PYTHON_BUILTIN_TYPES
    )
    merged = registry1.merge(registry2)
    assert merged.is_class("__module__.ClassA") is True
    assert merged.is_class("__module__.ClassB") is True
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

def use_constants():
    MAX_SIZE.bit_length()  # Should NOT be counted as class method
    DEFAULT_CONFIG.get("key")  # Should NOT be counted
    int.from_bytes(b"test", "big")  # Should be counted (int is built-in)
"""
    tree = ast.parse(source)
    registry = build_class_registry(tree)

    assert registry.is_class("MAX_SIZE") is False
    assert registry.is_class("DEFAULT_CONFIG") is False
    assert registry.is_class("PI") is False
    assert registry.is_class("int") is True  # Built-in
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
   - Accept ClassRegistry parameter
   - Add `_resolve_class_name()` method
   - Update `_extract_call_name()` to use resolver
   - Remove naive heuristics

4. **Update count_function_calls()** (30 min)
   - Build registry from AST
   - Pass to visitor

5. **Fix all existing tests** (45 min)
   - Update test files that instantiate `CallCountVisitor`
   - Files that need updating:
     - `tests/unit/test_call_counter.py` - Multiple test functions create CallCountVisitor
     - `tests/integration/test_end_to_end.py` - May need updates if it directly uses call_counter
   - Add class_registry parameter to all CallCountVisitor instantiations

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

## Success Criteria

1. **No False Positives**: Constants like `MAX_SIZE` are never treated as classes
2. **No False Negatives**: Non-PEP8 class names like `xmlParser` are correctly identified
3. **Built-in Support**: Python built-in types are recognized
4. **Nested Classes**: Correctly handle `Outer.Inner` patterns
5. **100% Test Coverage**: All new code has tests
6. **No Breaking Changes**: Existing tests still pass

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

---

**Next Steps After This:**
1. Implement unresolvable call reporting (requires knowing what's a class)
2. Then implement variable tracking (requires both class detection and unresolvable reporting)
