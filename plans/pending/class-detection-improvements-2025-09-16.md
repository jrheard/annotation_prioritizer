# Class Detection Improvements - Implementation Plan

**Date**: 2025-09-16
**Implementation Order**: This is step 1 of 3 in the single-file accuracy improvement sequence. This MUST be completed BEFORE unresolvable-call-reporting and scope-aware-variable-tracking.
**Timeline**: These improvements are for immediate implementation to achieve very accurate single-file analysis. Directory-wide analysis will begin in a few weeks.
**Goal**: Replace naive `name[0].isupper()` heuristics with accurate AST-based class detection and type registry system

## Problem Context

### Current Issues with Class Detection

The project currently uses a simple `name[0].isupper()` heuristic to detect classes in several locations:

```python
# Current problematic pattern found throughout codebase:
if name and name[0].isupper():
    # Assume it's a class - but this is wrong!
```

**Problems with this approach:**

1. **False Positives**: Constants like `MAX_SIZE`, `API_URL` are detected as classes
2. **False Negatives**: Non-PEP8 class names like `myClass`, `xmlParser` are missed
3. **Built-in Types**: Standard types like `str`, `int`, `list` are missed
4. **Import Aliases**: `from typing import List as MyList` creates detection failures
5. **String Annotations**: Forward references like `"Calculator"` aren't handled

### Examples of Current Failures

```python
# False positives (incorrectly detected as classes):
MAX_RETRIES = 3  # MAX_RETRIES[0].isupper() == True
API_ENDPOINT = "https://..."  # API_ENDPOINT[0].isupper() == True

# False negatives (missed classes):
class xmlParser:  # xmlParser[0].isupper() == False
    pass

class myCustomClass:  # myCustomClass[0].isupper() == False
    pass

# Built-in types missed:
def process_data(items: list) -> str:  # list, str not detected
    pass

# String annotations missed:
def create_calc() -> "Calculator":  # "Calculator" not detected
    pass
```

## Solution Overview

Implement a comprehensive class detection system that:

1. **AST-based tracking**: Use `visit_ClassDef` to track actual class definitions
2. **Built-in type registry**: Maintain registry of Python built-in types
3. **Confidence scoring**: Provide confidence levels for class detection
4. **Forward reference support**: Handle string annotations and two-pass resolution
5. **Import tracking**: Track class imports (future enhancement)
6. **Note**: @property decorators are excluded for now but noted for potential future reconsideration

## Implementation Steps

### Step 1: Create Class Registry Infrastructure

Create new module `src/annotation_prioritizer/class_registry.py`:

```python
"""Class detection and registry for accurate type resolution."""

from dataclasses import dataclass
from enum import StrEnum
from typing import frozenset


class ClassConfidence(StrEnum):
    """Confidence levels for class detection."""

    DEFINITE = "definite"      # AST-confirmed class definition
    BUILTIN = "builtin"        # Python built-in type
    LIKELY = "likely"          # Import or string annotation
    UNCERTAIN = "uncertain"    # Heuristic-based guess


@dataclass(frozen=True)
class ClassInfo:
    """Information about a detected class."""

    name: str                  # Class name (e.g., "Calculator")
    qualified_name: str        # Full name (e.g., "__module__.Calculator")
    confidence: ClassConfidence # How certain we are this is a class
    line_number: int | None    # Where defined (None for built-ins)
    is_builtin: bool          # Whether this is a Python built-in type


@dataclass(frozen=True)
class ClassRegistry:
    """Registry of all known classes in analysis scope."""

    classes: frozenset[ClassInfo]  # All detected classes

    def get_class_by_name(self, name: str) -> ClassInfo | None:
        """Get class info by simple name."""
        for cls in self.classes:
            if cls.name == name:
                return cls
        return None

    def get_class_by_qualified_name(self, qualified_name: str) -> ClassInfo | None:
        """Get class info by qualified name."""
        for cls in self.classes:
            if cls.qualified_name == qualified_name:
                return cls
        return None

    def is_class_name(self, name: str) -> bool:
        """Check if name is a known class."""
        return self.get_class_by_name(name) is not None

    def get_confidence(self, name: str) -> ClassConfidence | None:
        """Get confidence level for a class name."""
        cls = self.get_class_by_name(name)
        return cls.confidence if cls else None


def create_builtin_registry() -> frozenset[ClassInfo]:
    """Create registry of Python built-in types."""
    builtin_types = {
        # Basic types
        "int", "float", "str", "bool", "bytes", "bytearray",
        # Collections
        "list", "tuple", "dict", "set", "frozenset",
        # Other built-ins
        "object", "type", "None", "slice", "range",
        "memoryview", "property", "staticmethod", "classmethod",
        # Exception types (commonly used in annotations)
        "Exception", "ValueError", "TypeError", "AttributeError",
        "KeyError", "IndexError", "RuntimeError", "NotImplementedError",
    }

    return frozenset(
        ClassInfo(
            name=name,
            qualified_name=f"builtins.{name}",
            confidence=ClassConfidence.BUILTIN,
            line_number=None,
            is_builtin=True,
        )
        for name in builtin_types
    )
```

### Step 2: Implement AST-based Class Visitor

Add class detection to existing AST visitors. Update `function_parser.py`:

```python
# Add to FunctionDefinitionVisitor class:

def __init__(self, file_path: str) -> None:
    """Initialize the visitor with source file context."""
    super().__init__()
    self.functions: list[FunctionInfo] = []
    self._file_path = file_path
    self._scope_stack: list[Scope] = [Scope(kind=ScopeKind.MODULE, name="__module__")]
    # New: Track class definitions
    self._discovered_classes: list[ClassInfo] = []

@override
def visit_ClassDef(self, node: ast.ClassDef) -> None:
    """Track class definitions and scope context."""
    # Record the class definition
    qualified_name = self._build_qualified_name(node.name)
    class_info = ClassInfo(
        name=node.name,
        qualified_name=qualified_name,
        confidence=ClassConfidence.DEFINITE,
        line_number=node.lineno,
        is_builtin=False,
    )
    self._discovered_classes.append(class_info)

    # Continue with existing scope tracking
    self._scope_stack.append(Scope(kind=ScopeKind.CLASS, name=node.name))
    self.generic_visit(node)
    self._scope_stack.pop()

# Add public method to access discovered classes
def get_discovered_classes(self) -> tuple[ClassInfo, ...]:
    """Get all classes discovered during AST traversal."""
    return tuple(self._discovered_classes)
```

### Step 3: Create Two-Pass Analysis System

Implement forward reference resolution in new module `src/annotation_prioritizer/type_resolver.py`:

```python
"""Two-pass type resolution for handling forward references."""

import ast
from typing import override
from .models import FunctionInfo
from .class_registry import ClassRegistry, ClassInfo, ClassConfidence


class StringAnnotationExtractor(ast.NodeVisitor):
    """Extract type names from string annotations."""

    def __init__(self) -> None:
        super().__init__()
        self.extracted_types: set[str] = set()

    @override
    def visit_Constant(self, node: ast.Constant) -> None:
        """Extract type names from string constants in annotations."""
        if isinstance(node.value, str):
            # Simple extraction - just look for bare identifiers
            # More sophisticated parsing would handle Union["A", "B"] etc.
            type_name = node.value.strip().strip('"').strip("'")
            if type_name.isidentifier():
                self.extracted_types.add(type_name)
        self.generic_visit(node)


def extract_string_annotation_types(functions: tuple[FunctionInfo, ...]) -> frozenset[str]:
    """Extract all type names from string annotations in functions."""
    # This is a simplified implementation
    # Real implementation would parse the original AST and extract
    # string annotation contents, then parse those as type expressions

    # For now, return empty set - this will be enhanced in implementation
    return frozenset()


def build_complete_class_registry(
    ast_classes: tuple[ClassInfo, ...],
    string_annotation_types: frozenset[str],
) -> ClassRegistry:
    """Build complete class registry from multiple sources."""

    all_classes = set(ast_classes)

    # Add built-in types
    all_classes.update(create_builtin_registry())

    # Add string annotation types with lower confidence
    for type_name in string_annotation_types:
        # Only add if not already known with higher confidence
        if not any(cls.name == type_name for cls in all_classes):
            all_classes.add(ClassInfo(
                name=type_name,
                qualified_name=f"__module__.{type_name}",  # Assume module scope
                confidence=ClassConfidence.LIKELY,
                line_number=None,
                is_builtin=False,
            ))

    return ClassRegistry(classes=frozenset(all_classes))
```

### Step 4: Integrate Registry with Call Counter

Update `call_counter.py` to use class registry instead of heuristics:

```python
# Add to CallCountVisitor.__init__():
def __init__(self, known_functions: tuple[FunctionInfo, ...], class_registry: ClassRegistry) -> None:
    """Initialize visitor with functions to track and class registry."""
    super().__init__()
    self.call_counts: dict[str, int] = {func.qualified_name: 0 for func in known_functions}
    self._scope_stack: list[Scope] = [Scope(kind=ScopeKind.MODULE, name="__module__")]
    # New: Use class registry for accurate class detection
    self._class_registry = class_registry

# Update _extract_call_name method:
def _extract_call_name(self, node: ast.Call) -> str | None:
    """Extract the qualified name of the called function."""
    func = node.func

    # Direct calls to functions: function_name()
    if isinstance(func, ast.Name):
        return self._resolve_function_call(func.id)

    # Method calls: obj.method_name()
    if isinstance(func, ast.Attribute):
        # Self method calls: self.method_name()
        if isinstance(func.value, ast.Name) and func.value.id == "self":
            scope_names = [scope.name for scope in self._scope_stack if scope.kind != ScopeKind.FUNCTION]
            return ".".join([*scope_names, func.attr])

        # Static/class method calls: ClassName.method_name()
        if isinstance(func.value, ast.Name):
            class_name = func.value.id
            # NEW: Use registry instead of heuristic
            if self._class_registry.is_class_name(class_name):
                return f"__module__.{class_name}.{func.attr}"

        # Complex qualified calls
        if isinstance(func.value, ast.Attribute):
            return f"__module__.{func.attr}"

    return None
```

### Step 5: Update Main Analysis Pipeline

Update `analyzer.py` to incorporate class registry:

```python
# Add import
from .type_resolver import build_complete_class_registry, extract_string_annotation_types

def analyze_file(file_path: str) -> tuple[FunctionPriority, ...]:
    """Analyze a file and return prioritized functions."""
    # Parse functions (now also extracts classes)
    visitor = FunctionDefinitionVisitor(file_path)
    tree = ast.parse(Path(file_path).read_text(encoding="utf-8"))
    visitor.visit(tree)

    functions = visitor.get_functions()
    ast_classes = visitor.get_discovered_classes()

    # Extract string annotation types
    string_types = extract_string_annotation_types(functions)

    # Build complete class registry
    class_registry = build_complete_class_registry(ast_classes, string_types)

    # Count calls using class registry
    call_counts = count_function_calls(file_path, functions, class_registry)

    # Continue with existing analysis...
```

### Step 6: Add Comprehensive Test Coverage

Create `tests/unit/test_class_registry.py`:

```python
"""Tests for class detection and registry system."""

import pytest
from annotation_prioritizer.class_registry import (
    ClassRegistry, ClassInfo, ClassConfidence, create_builtin_registry
)


def test_builtin_registry_contains_common_types():
    """Test that built-in registry includes expected types."""
    registry = create_builtin_registry()
    builtin_names = {cls.name for cls in registry}

    # Check essential built-in types are present
    expected_types = {"int", "str", "list", "dict", "Exception"}
    assert expected_types.issubset(builtin_names)

    # Check all built-ins have correct properties
    for cls in registry:
        assert cls.confidence == ClassConfidence.BUILTIN
        assert cls.is_builtin is True
        assert cls.line_number is None
        assert cls.qualified_name.startswith("builtins.")


def test_class_registry_lookup_by_name():
    """Test class registry name-based lookup."""
    classes = frozenset([
        ClassInfo("Calculator", "__module__.Calculator", ClassConfidence.DEFINITE, 10, False),
        ClassInfo("Parser", "__module__.Parser", ClassConfidence.DEFINITE, 20, False),
    ])
    registry = ClassRegistry(classes)

    # Successful lookup
    calc = registry.get_class_by_name("Calculator")
    assert calc is not None
    assert calc.name == "Calculator"
    assert calc.line_number == 10

    # Failed lookup
    assert registry.get_class_by_name("NonExistent") is None


@pytest.mark.parametrize("test_input,expected", [
    ("Calculator", True),   # Known class
    ("Parser", True),       # Known class
    ("UnknownClass", False), # Unknown class
])
def test_is_class_name_detection(test_input: str, expected: bool):
    """Test class name detection with various inputs."""
    classes = frozenset([
        ClassInfo("Calculator", "__module__.Calculator", ClassConfidence.DEFINITE, 10, False),
        ClassInfo("Parser", "__module__.Parser", ClassConfidence.DEFINITE, 20, False),
    ])
    registry = ClassRegistry(classes)

    assert registry.is_class_name(test_input) == expected


def test_confidence_level_retrieval():
    """Test retrieving confidence levels for class names."""
    classes = frozenset([
        ClassInfo("Calculator", "__module__.Calculator", ClassConfidence.DEFINITE, 10, False),
        ClassInfo("MaybeClass", "__module__.MaybeClass", ClassConfidence.LIKELY, None, False),
    ])
    registry = ClassRegistry(classes)

    assert registry.get_confidence("Calculator") == ClassConfidence.DEFINITE
    assert registry.get_confidence("MaybeClass") == ClassConfidence.LIKELY
    assert registry.get_confidence("NonExistent") is None
```

Create `tests/unit/test_class_detection.py`:

```python
"""Tests for AST-based class detection."""

import ast
import pytest
from annotation_prioritizer.function_parser import FunctionDefinitionVisitor
from annotation_prioritizer.class_registry import ClassInfo, ClassConfidence


def test_class_definition_detection():
    """Test detection of class definitions via AST."""
    source = '''
class Calculator:
    def add(self, a, b):
        return a + b

class Parser:
    pass

def function():
    pass
'''

    tree = ast.parse(source)
    visitor = FunctionDefinitionVisitor("test.py")
    visitor.visit(tree)

    classes = visitor.get_discovered_classes()
    assert len(classes) == 2

    # Check Calculator class
    calc_class = next(cls for cls in classes if cls.name == "Calculator")
    assert calc_class.qualified_name == "__module__.Calculator"
    assert calc_class.confidence == ClassConfidence.DEFINITE
    assert calc_class.line_number == 2  # Line where class is defined
    assert calc_class.is_builtin is False


def test_nested_class_detection():
    """Test detection of nested classes."""
    source = '''
class Outer:
    class Inner:
        def method(self):
            pass

    def outer_method(self):
        pass
'''

    tree = ast.parse(source)
    visitor = FunctionDefinitionVisitor("test.py")
    visitor.visit(tree)

    classes = visitor.get_discovered_classes()
    class_names = {cls.qualified_name for cls in classes}

    assert "__module__.Outer" in class_names
    assert "__module__.Outer.Inner" in class_names


@pytest.mark.parametrize("source,expected_classes", [
    # Empty file
    ("", []),
    # Only functions
    ("def func(): pass", []),
    # Only classes
    ("class A: pass\nclass B: pass", ["__module__.A", "__module__.B"]),
    # Mixed content
    ("class A: pass\ndef func(): pass\nclass B: pass", ["__module__.A", "__module__.B"]),
])
def test_class_detection_edge_cases(source: str, expected_classes: list[str]):
    """Test class detection with various source code patterns."""
    tree = ast.parse(source)
    visitor = FunctionDefinitionVisitor("test.py")
    visitor.visit(tree)

    classes = visitor.get_discovered_classes()
    actual_names = [cls.qualified_name for cls in classes]

    assert sorted(actual_names) == sorted(expected_classes)
```

Create `tests/integration/test_class_detection_integration.py`:

```python
"""Integration tests for class detection improvements."""

import tempfile
from pathlib import Path
from annotation_prioritizer.analyzer import analyze_file


def test_class_detection_fixes_false_positives():
    """Test that constants are not detected as classes."""
    source = '''
MAX_RETRIES = 3
API_ENDPOINT = "https://example.com"

class Calculator:
    def add(self, a, b):
        return a + b

def process():
    calc = Calculator()
    return calc.add(1, 2)
'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(source)
        f.flush()

        try:
            priorities = analyze_file(f.name)

            # Calculator.add should be detected and have calls counted
            calc_add = next((p for p in priorities if "Calculator.add" in p.function_info.qualified_name), None)
            assert calc_add is not None
            assert calc_add.call_count == 1  # Should count calc.add(1, 2)

        finally:
            Path(f.name).unlink()


def test_class_detection_handles_non_pep8_names():
    """Test that non-PEP8 class names are detected correctly."""
    source = '''
class xmlParser:  # Non-PEP8 name
    def parse(self, data):
        return data

class myCustomClass:  # Another non-PEP8 name
    def process(self):
        pass

def use_classes():
    parser = xmlParser()
    custom = myCustomClass()
    parser.parse("data")
    custom.process()
'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(source)
        f.flush()

        try:
            priorities = analyze_file(f.name)

            # Both methods should be detected and have calls counted
            parser_parse = next((p for p in priorities if "xmlParser.parse" in p.function_info.qualified_name), None)
            custom_process = next((p for p in priorities if "myCustomClass.process" in p.function_info.qualified_name), None)

            assert parser_parse is not None
            assert parser_parse.call_count == 1

            assert custom_process is not None
            assert custom_process.call_count == 1

        finally:
            Path(f.name).unlink()


def test_builtin_type_recognition():
    """Test that built-in types are recognized correctly."""
    source = '''
def process_data(items: list) -> str:
    return str(len(items))

def call_builtin_methods():
    data = [1, 2, 3]
    result = str.join(",", ["a", "b"])  # str.join static method call
    return result
'''

    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(source)
        f.flush()

        try:
            priorities = analyze_file(f.name)

            # Should not crash and should handle built-in types gracefully
            # This is more of a regression test to ensure no errors occur
            assert len(priorities) >= 1  # At least process_data should be found

        finally:
            Path(f.name).unlink()
```

### Step 7: Performance Considerations

Since class detection adds overhead, ensure efficient implementation:

```python
# In ClassRegistry, use frozenset for O(1) lookups
@dataclass(frozen=True)
class ClassRegistry:
    classes: frozenset[ClassInfo]
    # Cache for fast lookups
    _name_lookup: dict[str, ClassInfo] = field(init=False)
    _qualified_name_lookup: dict[str, ClassInfo] = field(init=False)

    def __post_init__(self):
        # Build lookup caches
        name_lookup = {}
        qualified_lookup = {}
        for cls in self.classes:
            name_lookup[cls.name] = cls
            qualified_lookup[cls.qualified_name] = cls

        object.__setattr__(self, '_name_lookup', name_lookup)
        object.__setattr__(self, '_qualified_name_lookup', qualified_lookup)

    def get_class_by_name(self, name: str) -> ClassInfo | None:
        """O(1) lookup by simple name."""
        return self._name_lookup.get(name)
```

## Future Work

### Phase 2: Import Resolution
Once basic class detection is working, enhance with import tracking:

```python
# Track imports in AST visitor
@override
def visit_Import(self, node: ast.Import) -> None:
    """Track imported modules and classes."""
    for alias in node.names:
        # Track: import module, import module as alias
        pass

@override
def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
    """Track from-imports of classes."""
    for alias in node.names:
        # Track: from module import Class, from module import Class as Alias
        pass
```

### Phase 3: String Annotation Parsing
Enhance string annotation handling:

```python
def parse_string_annotation(annotation: str) -> set[str]:
    """Parse string annotation to extract type names."""
    # Handle complex cases:
    # "Union[Calculator, Parser]" -> {"Calculator", "Parser"}
    # "List[Calculator]" -> {"List", "Calculator"}
    # "Optional[Calculator]" -> {"Optional", "Calculator"}
    pass
```

### Phase 4: Property Decorator Support
Add support for `@property` decorated methods:

```python
@override
def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
    """Process function, checking for property decorators."""
    has_property = any(
        isinstance(dec, ast.Name) and dec.id == "property"
        for dec in node.decorator_list
    )

    if has_property:
        # Properties are accessed like attributes, not called like methods
        # This affects call counting logic
        pass
```

## Success Criteria

1. **Accuracy**: No more false positives from constants like `MAX_SIZE`
2. **Completeness**: Non-PEP8 class names like `xmlParser` are detected
3. **Built-in Support**: Standard types like `str`, `list` are recognized
4. **Performance**: No significant slowdown in analysis time
5. **Test Coverage**: 100% coverage maintained for all new code
6. **Integration**: Works seamlessly with existing scope infrastructure

## Dependencies

- **Scope Infrastructure**: ✅ Already implemented (typed `Scope`/`ScopeKind`)
- **AST Visitor Pattern**: ✅ Already established in function parser and call counter
- **Frozen Dataclass Pattern**: ✅ Already used throughout project
- **Pure Function Design**: ✅ Follows project's functional programming style

## Implementation Notes

1. **Start Small**: Begin with basic AST-based detection before adding complexity
2. **Maintain Backward Compatibility**: Ensure existing function parser interface unchanged
3. **Conservative Approach**: When uncertain about class detection, prefer lower confidence over false positives
4. **Test-Driven**: Write tests for each component before implementation
5. **Document Edge Cases**: Clear documentation of what is and isn't supported

This plan provides a solid foundation for accurate class detection while maintaining the project's design principles and test coverage requirements.
