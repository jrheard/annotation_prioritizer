# QualifiedName NewType Implementation Plan

## Problem Statement

The codebase extensively uses qualified names (e.g., `"__module__.Calculator.add"`) to uniquely identify functions across different scopes. Currently, these are represented as plain `str` types throughout the codebase, leading to:

1. **Type confusion**: Functions accepting or returning qualified names have ambiguous signatures
2. **Runtime checks**: Test factories include assertions like `assert "." not in name` to prevent mixing simple and qualified names
3. **Silent failures**: Dictionary lookups between `CallCount` and `FunctionInfo` fail silently if names don't match exactly
4. **Poor documentation**: Developers must read comments to understand whether a `str` parameter expects a simple or qualified name

## Benefits of QualifiedName NewType

- **Compile-time safety**: Type checker catches mixing of simple and qualified names
- **Self-documenting code**: Function signatures clearly indicate expected name types
- **Reduced runtime checks**: Type system enforces constraints previously checked at runtime
- **Better IDE support**: Auto-completion and type hints work correctly

## Implementation Steps

### Commit 1: Introduce QualifiedName type and update all data models

**Files to modify:**
- `src/annotation_prioritizer/models.py`

**Changes:**

Add the NewType and helper functions at the top of models.py:
```python
from typing import NewType

# Define the new type for qualified names like "__module__.ClassName.method"
QualifiedName = NewType('QualifiedName', str)

def make_qualified_name(name: str) -> QualifiedName:
    """Create a QualifiedName from a string.

    This is the only way to create a QualifiedName, ensuring type safety.

    Args:
        name: A qualified name string like "__module__.ClassName.method"

    Returns:
        A QualifiedName instance
    """
    return QualifiedName(name)
```

Update the data models to use QualifiedName:
```python
@dataclass(frozen=True)
class FunctionInfo:
    name: str  # Local function name (e.g., 'add')
    qualified_name: QualifiedName  # Changed from str
    parameters: tuple[ParameterInfo, ...]
    has_return_annotation: bool
    line_number: int
    file_path: str

@dataclass(frozen=True)
class CallCount:
    function_qualified_name: QualifiedName  # Changed from str
    call_count: int

@dataclass(frozen=True)
class AnnotationScore:
    function_qualified_name: QualifiedName  # Changed from str
    parameter_score: float
    return_score: float
    total_score: float
```

**Why this grouping:** Introducing the type and updating models together ensures the foundation is in place before we start using it elsewhere.

### Commit 2: Update all qualified name producers

**Files to modify:**
- `src/annotation_prioritizer/scope_tracker.py`
- `src/annotation_prioritizer/function_parser.py`
- `src/annotation_prioritizer/class_discovery.py`

**Changes to scope_tracker.py:**
```python
from annotation_prioritizer.models import QualifiedName, make_qualified_name

def build_qualified_name(
    scope_stack: ScopeStack,
    name: str,
    exclude_kinds: frozenset[ScopeKind] | None = None
) -> QualifiedName:  # Changed return type
    """Build a qualified name from scope stack with optional filtering."""
    exclude_kinds = exclude_kinds or frozenset()
    filtered = [s.name for s in scope_stack if s.kind not in exclude_kinds]
    return make_qualified_name(".".join([*filtered, name]))

def generate_name_candidates(
    scope_stack: ScopeStack,
    name: str
) -> tuple[QualifiedName, ...]:  # Changed return type
    """Generate all possible qualified names from innermost to outermost scope."""
    candidates: list[QualifiedName] = []
    for i in range(len(scope_stack) - 1, -1, -1):
        prefix = ".".join(s.name for s in scope_stack[: i + 1])
        candidates.append(make_qualified_name(f"{prefix}.{name}"))
    return tuple(candidates)

def get_containing_class(stack: ScopeStack) -> QualifiedName | None:  # Changed return type
    """Get the qualified name of the containing class, if any."""
    for i in range(len(stack) - 1, -1, -1):
        if stack[i].kind == ScopeKind.CLASS:
            return make_qualified_name(".".join(s.name for s in stack[: i + 1]))
    return None

def find_first_match(
    candidates: tuple[QualifiedName, ...],  # Changed parameter type
    registry: AbstractSet[QualifiedName]  # Changed parameter type
) -> QualifiedName | None:
    """Check candidates against a registry and return first match."""
    return first(candidates, lambda c: c in registry)
```

**Changes to function_parser.py:**
```python
from annotation_prioritizer.models import QualifiedName, make_qualified_name

# In FunctionVisitor class:
def _build_qualified_name(self, function_name: str) -> QualifiedName:
    """Construct a fully qualified name using the current scope context."""
    scope_names = [scope.name for scope in self._scope_stack]
    return make_qualified_name(".".join([*scope_names, function_name]))
```

**Changes to class_discovery.py:**
```python
from annotation_prioritizer.models import QualifiedName, make_qualified_name

@dataclass(frozen=True)
class ClassRegistry:
    ast_classes: frozenset[QualifiedName]  # Changed from frozenset[str]
    builtin_classes: frozenset[str]  # Keep as str for builtins

    def is_class(self, name: str | QualifiedName) -> bool:
        """Check if a name refers to a known class."""
        if isinstance(name, QualifiedName):
            return name in self.ast_classes or str(name) in self.builtin_classes
        else:
            # Check builtins first (simple names)
            if name in self.builtin_classes:
                return True
            # Check AST classes (convert string for comparison)
            return any(str(qn) == name for qn in self.ast_classes)

class ClassDiscoveryVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        super().__init__()
        self.class_names: list[QualifiedName] = []  # Changed type
        self._scope_stack = create_initial_stack()

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Record class definition with full qualified name."""
        scope_names = [scope.name for scope in self._scope_stack]
        qualified_name = make_qualified_name(".".join([*scope_names, node.name]))
        self.class_names.append(qualified_name)
        # ... rest of method ...

def build_class_registry(tree: ast.AST) -> ClassRegistry:
    """Build a registry of all classes defined in the AST."""
    visitor = ClassDiscoveryVisitor()
    visitor.visit(tree)
    return ClassRegistry(
        ast_classes=frozenset(visitor.class_names),  # Now QualifiedName
        builtin_classes=PYTHON_BUILTINS
    )
```

**Why this grouping:** All functions that create qualified names are updated together, ensuring consistent production of the new type.

### Commit 3: Update all qualified name consumers

**Files to modify:**
- `src/annotation_prioritizer/call_counter.py`
- `src/annotation_prioritizer/analyzer.py`
- `src/annotation_prioritizer/scoring.py`

**Changes to call_counter.py:**
```python
from annotation_prioritizer.models import QualifiedName, make_qualified_name

def count_function_calls(
    file_path: str,
    known_functions: tuple[FunctionInfo, ...]
) -> tuple[CallCount, ...]:
    # ... existing code ...
    return tuple(
        CallCount(function_qualified_name=name, call_count=count)
        for name, count in visitor.call_counts.items()
    )

class CallCountVisitor(ast.NodeVisitor):
    def __init__(self, known_functions: tuple[FunctionInfo, ...], class_registry: ClassRegistry):
        super().__init__()
        # Dictionary now uses QualifiedName as keys
        self.call_counts: dict[QualifiedName, int] = {
            func.qualified_name: 0 for func in known_functions
        }
        self._class_registry = class_registry
        self._scope_stack = create_initial_stack()

    def visit_Call(self, node: ast.Call) -> None:
        """Visit function call to count calls to known functions."""
        call_name = self._resolve_call_name(node)
        if call_name and call_name in self.call_counts:
            self.call_counts[call_name] += 1
        self.generic_visit(node)

    def _resolve_call_name(self, node: ast.Call) -> QualifiedName | None:
        """Resolve the qualified name of the called function."""
        # ... returns QualifiedName or None ...

    def _resolve_function_call(self, function_name: str) -> QualifiedName | None:
        """Resolve a direct function call to its qualified name."""
        candidates = generate_name_candidates(self._scope_stack, function_name)
        return find_first_match(candidates, self.call_counts.keys())

    def _resolve_class_name(self, class_name: str) -> QualifiedName | None:
        """Resolve a class name to its qualified form based on current scope."""
        candidates = generate_name_candidates(self._scope_stack, class_name)
        for candidate in candidates:
            if self._class_registry.is_class(candidate):
                return candidate
        # Check if it's a built-in
        if self._class_registry.is_class(class_name):
            return make_qualified_name(class_name)
        return None

    def _resolve_method_call(self, func: ast.Attribute) -> QualifiedName | None:
        """Resolve qualified name from a method call."""
        if isinstance(func.value, ast.Name) and func.value.id in ("self", "cls"):
            return build_qualified_name(
                self._scope_stack, func.attr,
                exclude_kinds=frozenset({ScopeKind.FUNCTION})
            )

        class_name = self._extract_class_name_from_value(func.value)
        if not class_name:
            return None

        resolved_class = self._resolve_class_name(class_name)
        if resolved_class:
            return make_qualified_name(f"{str(resolved_class)}.{func.attr}")
        return None
```

**Changes to analyzer.py:**
```python
from annotation_prioritizer.models import QualifiedName

def analyze_file(file_path: str) -> tuple[FunctionPriority, ...]:
    """Complete analysis pipeline for a single Python file."""
    function_infos = parse_function_definitions(file_path)
    if not function_infos:
        return ()

    call_counts = count_function_calls(file_path, function_infos)
    # Dictionary now uses QualifiedName as keys
    call_count_map: dict[QualifiedName, int] = {
        cc.function_qualified_name: cc.call_count for cc in call_counts
    }

    priorities: list[FunctionPriority] = []
    for func_info in function_infos:
        annotation_score = calculate_annotation_score(func_info)
        call_count = call_count_map.get(func_info.qualified_name, 0)
        priority_score = calculate_priority_score(annotation_score, call_count)

        priority = FunctionPriority(
            function_info=func_info,
            annotation_score=annotation_score,
            call_count=call_count,
            priority_score=priority_score,
        )
        priorities.append(priority)

    return tuple(sorted(priorities, key=lambda p: p.priority_score, reverse=True))
```

**Changes to scoring.py:**
```python
# The scoring.py file will automatically work with the new type since
# it receives FunctionInfo objects that now have QualifiedName fields
```

**Why this grouping:** All code that consumes qualified names is updated together, completing the type migration in production code.

### Commit 4: Update all tests and remove obsolete runtime checks

**Files to modify:**
- `tests/helpers/factories.py`
- `tests/unit/test_*.py`
- `tests/integration/test_*.py`

**Changes to factories.py:**
```python
from annotation_prioritizer.models import QualifiedName, make_qualified_name

def make_function_info(
    name: str = "test_func",
    *,
    qualified_name: QualifiedName | None = None,  # Accept QualifiedName
    parameters: tuple[ParameterInfo, ...] | None = None,
    has_return_annotation: bool = False,
    line_number: int = 1,
    file_path: str = "/test.py",
) -> FunctionInfo:
    """Create FunctionInfo with sensible defaults."""
    if qualified_name is None:
        # Type system now ensures this is correct
        qualified_name = make_qualified_name(f"__module__.{name}")
    if parameters is None:
        parameters = ()

    return FunctionInfo(
        name=name,
        qualified_name=qualified_name,
        parameters=parameters,
        has_return_annotation=has_return_annotation,
        line_number=line_number,
        file_path=file_path,
    )

def make_priority(
    name: str = "test_func",
    *,
    # ... other parameters ...
) -> FunctionPriority:
    """Create FunctionPriority with explicit values."""
    # Keep assertion for now - ensures test correctness
    assert "." not in name, f"Function name should not be qualified, got: {name}"

    qualified_name = make_qualified_name(f"__module__.{name}")
    # ... rest of function using qualified_name ...
```

**Example test updates:**
```python
# In test files, update comparisons and assertions:

# Before:
assert func.qualified_name == "__module__.simple_function"

# After:
assert str(func.qualified_name) == "__module__.simple_function"
# Or better:
assert func.qualified_name == make_qualified_name("__module__.simple_function")

# When using qualified names as dict keys:
call_counts = {c.function_qualified_name: c.call_count for c in counts}
# This works as-is since QualifiedName is hashable

# When checking qualified names in sets:
qualified_names = {p.function_info.qualified_name for p in priorities}
expected = {
    make_qualified_name("__module__.Calculator.add"),
    make_qualified_name("__module__.Calculator.multiply"),
}
assert qualified_names == expected
```

**Why this grouping:** All test updates are done together as the final step, ensuring tests pass with the new type system.

## Testing Strategy

Each commit should:
1. Pass type checking with `pyright`
2. Pass all existing tests with `pytest`
3. Maintain 100% test coverage
4. Pass linting with `ruff check` and `ruff format`

## Key Considerations

- **NewType behavior**: At runtime, `QualifiedName` is still a `str`, so serialization and comparison work normally
- **String operations**: When string methods are needed, use `str(qualified_name)`
- **Type narrowing**: The `is_class` method in `ClassRegistry` accepts both `str` and `QualifiedName` for flexibility
- **Backward compatibility**: The changes are internal only, no external API changes

## Migration Benefits

After this implementation:
1. Function signatures become self-documenting
2. Type checker catches name type mismatches at development time
3. IDE support improves with better autocomplete
4. Code becomes more maintainable and less error-prone
5. Runtime assertions can potentially be removed in the future
