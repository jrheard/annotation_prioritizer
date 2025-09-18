# Unresolvable Call Reporting Implementation Plan

**Created**: 2025-09-16
**Priority**: HIGH - Provides critical transparency about analysis coverage
**Prerequisites**: class-detection-improvements-2025-09-16.md MUST be completed first

## Executive Summary

This plan adds transparency to the call counter by reporting calls it cannot resolve rather than silently ignoring them. Users will understand exactly what the tool can and cannot analyze, building trust through transparency rather than false confidence.

**Key principle**: "I don't know" is better than wrong guesses or silent failures.

## Problem Statement

### Current Silent Failures

The call counter currently returns `None` for unresolvable calls and silently ignores them:

```python
# Current behavior in call_counter.py
def _resolve_call_name(self, node: ast.Call) -> QualifiedName | None:
    # ... attempts to resolve ...
    # Dynamic calls: getattr(obj, 'method')(), obj[key](), etc.
    # Cannot be resolved statically - return None
    return None  # Silently ignored! User has no idea this call was skipped
```

### Impact on Users

Users see "Function called 3 times" without knowing that:
- 7 other calls were silently ignored
- Dynamic calls like `getattr(obj, 'method')()` aren't counted
- Import-based calls aren't tracked yet
- Complex attribute chains might fail to resolve

This undermines trust and makes it impossible to assess coverage completeness.

### Concrete Examples

```python
# These work and are counted:
DataProcessor.utility_function("hello")  # Static method call
self.method_name()  # Self method call within class

# These are silently ignored (no tracking/reporting):
# INSTANCE_METHOD - Instance method calls via variables:
processor = DataProcessor(config)
processor.process_data(data)  # Shows 0 calls - silently ignored!

# GETATTR - Dynamic calls using getattr:
method = getattr(processor, 'process_data')
result = method(data)  # getattr call - unresolvable

# SUBSCRIPT - Dictionary/subscript dispatch:
handlers = {'process': processor.process_data}
handlers['process'](data)  # Subscript call - unresolvable

# EVAL - Dynamic code execution:
eval("processor.process_data(data)")  # eval call - unresolvable

# COMPLEX_QUALIFIED - Deep attribute chains:
app.services.database.connection.execute(query)  # Too deep to resolve

# IMPORTED - Calls to imported functions (not yet implemented):
from math import sqrt
sqrt(16)  # Import tracking not yet supported

import json
json.dumps({'key': 'value'})  # Module function calls not tracked

# UNKNOWN - Edge cases that don't fit other categories:
(lambda x: x * 2)(5)  # Lambda calls
callable_obj = SomeClass()
callable_obj(args)  # Calls to callable objects (__call__ method)
```

## Technical Design

### 1. New Data Models

Add to `models.py`:

```python
from enum import StrEnum

class UnresolvableCategory(StrEnum):
    """Categories for why a call couldn't be resolved."""
    GETATTR = "getattr"  # getattr() dynamic attribute access
    SUBSCRIPT = "subscript"  # Dictionary/list subscript calls: obj[key]()
    EVAL = "eval"  # eval() or exec() dynamic code execution
    IMPORTED = "imported"  # Calls to imported functions (not yet supported)
    COMPLEX_QUALIFIED = "complex_qualified"  # Deep attribute chains
    INSTANCE_METHOD = "instance_method"  # obj.method() where obj is a variable
    UNKNOWN = "unknown"  # Doesn't fit other categories

@dataclass(frozen=True)
class UnresolvableCall:
    """Information about a call that couldn't be resolved.

    Provides context about why the tool couldn't count a specific call,
    helping users understand coverage limitations.
    """
    line_number: int  # Line where the unresolvable call appears
    call_text: str  # First 1000 chars of the call for context
    category: UnresolvableCategory  # Why it couldn't be resolved

@dataclass(frozen=True)
class CallCountResult:
    """Enhanced result including both resolved and unresolved calls.

    Provides full transparency about what was and wasn't counted,
    allowing users to assess the completeness of the analysis.
    """
    resolved_counts: tuple[CallCount, ...]  # Successfully resolved
    unresolvable_count: int  # Total number we couldn't resolve
    unresolvable_examples: tuple[UnresolvableCall, ...]  # First 5 for debugging
```

### 2. Categorization Logic

Create new pure function in `call_counter.py`:

```python
def categorize_unresolvable_call(node: ast.Call, source_lines: tuple[str, ...]) -> UnresolvableCall:
    """Categorize why a call couldn't be resolved.

    Pure function that examines the AST node structure to determine
    why the call is unresolvable, providing transparency for users.

    Args:
        node: The unresolvable call AST node
        source_lines: Source code lines for extracting call text

    Returns:
        UnresolvableCall with category and context
    """
    # Extract call text (first 1000 chars for context)
    line_idx = node.lineno - 1  # Convert to 0-indexed
    if 0 <= line_idx < len(source_lines):
        line = source_lines[line_idx]
        # Find the call in the line (approximate)
        call_start = node.col_offset
        call_text = line[call_start:call_start + 1000].strip()
    else:
        call_text = "<unable to extract call text>"

    # Categorize based on AST structure
    func = node.func

    # getattr() calls
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Call):
        if isinstance(func.value.func, ast.Name):
            if func.value.func.id == "getattr":
                return UnresolvableCall(
                    line_number=node.lineno,
                    call_text=call_text,
                    category=UnresolvableCategory.GETATTR
                )

    # Dictionary/subscript calls: obj[key]()
    if isinstance(func, ast.Subscript):
        return UnresolvableCall(
            line_number=node.lineno,
            call_text=call_text,
            category=UnresolvableCategory.SUBSCRIPT
        )

    # eval() or exec() calls
    if isinstance(func, ast.Call):
        if isinstance(func.func, ast.Name) and func.func.id in ("eval", "exec"):
            return UnresolvableCall(
                line_number=node.lineno,
                call_text=call_text,
                category=UnresolvableCategory.EVAL
            )

    # Instance method calls: variable.method() where variable is not self/cls
    # and doesn't start with uppercase (likely not a class name)
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
        if func.value.id not in ("self", "cls") and not func.value.id[0].isupper():
            return UnresolvableCall(
                line_number=node.lineno,
                call_text=call_text,
                category=UnresolvableCategory.INSTANCE_METHOD
            )

    # Complex qualified calls we can't resolve
    if isinstance(func, ast.Attribute):
        # Count depth of attribute chain
        depth = 0
        current = func
        while isinstance(current, ast.Attribute):
            depth += 1
            current = current.value

        if depth > 2:  # e.g., a.b.c.d()
            return UnresolvableCall(
                line_number=node.lineno,
                call_text=call_text,
                category=UnresolvableCategory.COMPLEX_QUALIFIED
            )

    # Default category for unrecognized patterns
    return UnresolvableCall(
        line_number=node.lineno,
        call_text=call_text,
        category=UnresolvableCategory.UNKNOWN
    )
```

### 3. Update CallCountVisitor

Modify `CallCountVisitor` class:

```python
class CallCountVisitor(ast.NodeVisitor):
    """Enhanced visitor that tracks both resolved and unresolved calls."""

    def __init__(self, known_functions: tuple[FunctionInfo, ...],
                 class_registry: ClassRegistry,
                 source_lines: tuple[str, ...]) -> None:
        """Initialize with source lines for unresolvable call context."""
        super().__init__()
        self.call_counts: dict[QualifiedName, int] = {func.qualified_name: 0 for func in known_functions}
        self._class_registry = class_registry
        self._scope_stack = create_initial_stack()

        # New: Track unresolvable calls
        self._source_lines = source_lines
        self._unresolvable_calls: list[UnresolvableCall] = []

    @override
    def visit_Call(self, node: ast.Call) -> None:
        """Visit call, tracking both resolved and unresolved."""
        call_name = self._resolve_call_name(node)

        if call_name and call_name in self.call_counts:
            self.call_counts[call_name] += 1
        elif call_name is None:
            # New: Track unresolvable calls
            unresolvable = categorize_unresolvable_call(node, self._source_lines)
            self._unresolvable_calls.append(unresolvable)

        self.generic_visit(node)

    def get_result(self) -> CallCountResult:
        """Build complete result with resolved and unresolved calls."""
        resolved = tuple(
            CallCount(function_qualified_name=name, call_count=count)
            for name, count in self.call_counts.items()
        )

        # Limit examples to first 5 for manageable output
        examples = tuple(self._unresolvable_calls[:5])

        return CallCountResult(
            resolved_counts=resolved,
            unresolvable_count=len(self._unresolvable_calls),
            unresolvable_examples=examples
        )
```

### 4. Update count_function_calls()

Modify the main function:

```python
def count_function_calls(
    file_path: str,
    known_functions: tuple[FunctionInfo, ...]
) -> CallCountResult:
    """Count calls with full transparency about resolved and unresolved.

    Returns CallCountResult with both successful resolutions and
    information about calls that couldn't be resolved.
    """
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        return CallCountResult(
            resolved_counts=(),
            unresolvable_count=0,
            unresolvable_examples=()
        )

    try:
        source_code = file_path_obj.read_text(encoding="utf-8")
        source_lines = tuple(source_code.splitlines())
        tree = ast.parse(source_code, filename=file_path)
    except (OSError, SyntaxError):
        return CallCountResult(
            resolved_counts=(),
            unresolvable_count=0,
            unresolvable_examples=()
        )

    class_registry = build_class_registry(tree)
    visitor = CallCountVisitor(known_functions, class_registry, source_lines)
    visitor.visit(tree)

    return visitor.get_result()
```

### 5. Update Analyzer

Modify `analyzer.py` to handle new result type:

```python
def analyze_file(file_path: str) -> tuple[FunctionPriority, ...]:
    """Analyze file with transparency about unresolved calls."""
    # Parse functions
    functions = parse_functions(file_path)
    if not functions:
        return ()

    # Count calls (new: get full result)
    call_result = count_function_calls(file_path, functions)

    # Build lookup from resolved counts (maintains existing logic)
    call_count_lookup = {
        cc.function_qualified_name: cc.call_count
        for cc in call_result.resolved_counts
    }

    # Rest of the function remains the same...
    # (Store call_result for potential future use in reporting)
```

### 6. CLI Integration

Add optional flag to `cli.py`:

```python
def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Analyze Python files to prioritize type annotation additions"
    )
    parser.add_argument("target", help="Python file to analyze", type=Path)
    parser.add_argument(
        "--min-calls",
        type=int,
        default=0,
        help="Filter functions with fewer than N calls (default: 0)",
    )
    # New flag
    parser.add_argument(
        "--show-unresolvable",
        action="store_true",
        help="Show details about calls that couldn't be resolved",
    )
    return parser.parse_args()
```

Update main() to handle unresolvable reporting:

```python
def main() -> None:
    """Run the CLI application."""
    console = Console()
    args = parse_args()

    # ... validation code ...

    try:
        # Analyze the file
        priorities = analyze_file(str(args.target))

        # New: Get unresolvable info if requested
        if args.show_unresolvable:
            # Re-parse to get unresolvable info
            functions = parse_functions(str(args.target))
            call_result = count_function_calls(str(args.target), functions)

            # Display unresolvable summary
            display_unresolvable_summary(console, call_result)

        # ... rest of existing code ...
```

### 7. Output Formatting

Add to `output.py`:

```python
def display_unresolvable_summary(console: Console, result: CallCountResult) -> None:
    """Display summary of unresolvable calls."""
    total_calls = sum(cc.call_count for cc in result.resolved_counts)
    total_attempted = total_calls + result.unresolvable_count

    if result.unresolvable_count == 0:
        console.print("[green]✓ All calls resolved successfully[/green]")
        return

    # Summary
    console.print(
        f"\n[yellow]Call Resolution Summary:[/yellow]\n"
        f"  Resolved: {total_calls}/{total_attempted} calls "
        f"({100 * total_calls / total_attempted:.1f}%)\n"
        f"  Unresolvable: {result.unresolvable_count} calls\n"
    )

    # Category breakdown
    if result.unresolvable_examples:
        categories = {}
        for example in result.unresolvable_examples:
            categories[example.category] = categories.get(example.category, 0) + 1

        console.print("[yellow]Unresolvable Categories:[/yellow]")
        for category, count in sorted(categories.items()):
            console.print(f"  {category}: {count} example(s)")

    # Examples
    if result.unresolvable_examples:
        console.print("\n[yellow]Example Unresolvable Calls:[/yellow]")
        for example in result.unresolvable_examples[:3]:  # Show max 3
            console.print(
                f"  Line {example.line_number}: {example.call_text} "
                f"[{example.category}]"
            )
```

## Testing Strategy

### Unit Tests

#### Test categorize_unresolvable_call()

```python
def test_categorize_getattr_call():
    """Test categorizing getattr() as GETATTR."""
    source = "result = getattr(obj, 'method')()"
    node = ast.parse(source).body[0].value
    result = categorize_unresolvable_call(node, (source,))

    assert result.category == UnresolvableCategory.GETATTR
    assert result.line_number == 1
    assert "getattr" in result.call_text

def test_categorize_subscript_call():
    """Test categorizing obj[key]() as SUBSCRIPT."""
    source = "result = handlers[event_type](data)"
    node = ast.parse(source).body[0].value
    result = categorize_unresolvable_call(node, (source,))

    assert result.category == UnresolvableCategory.SUBSCRIPT
    assert "handlers[event_type]" in result.call_text

def test_categorize_eval_call():
    """Test categorizing eval() and exec() as EVAL."""
    source = "result = eval('func()')"
    node = ast.parse(source).body[0].value
    result = categorize_unresolvable_call(node, (source,))

    assert result.category == UnresolvableCategory.EVAL
    assert "eval" in result.call_text

def test_categorize_complex_qualified():
    """Test categorizing deep attribute chains."""
    source = "result = a.b.c.d.method()"
    node = ast.parse(source).body[0].value
    result = categorize_unresolvable_call(node, (source,))

    assert result.category == UnresolvableCategory.COMPLEX_QUALIFIED
```

#### Test CallCountResult

```python
def test_call_count_result_with_unresolvable():
    """Test CallCountResult with both resolved and unresolved."""
    source = '''
def func1(): pass
def func2(): pass

func1()  # Resolved
getattr(obj, 'method')()  # Unresolved
func2()  # Resolved
handlers[key]()  # Unresolved
'''
    # ... setup and run ...

    assert len(result.resolved_counts) == 2
    assert result.unresolvable_count == 2
    assert len(result.unresolvable_examples) == 2

def test_unresolvable_examples_limited_to_five():
    """Test that only first 5 unresolvable calls are kept as examples."""
    # Create source with 10 unresolvable calls
    # Verify only 5 examples are returned
```

### Integration Tests

```python
def test_backward_compatibility():
    """Test that legacy interface still works."""
    result = count_function_calls_legacy("test.py", functions)
    assert isinstance(result, tuple)
    assert all(isinstance(cc, CallCount) for cc in result)

def test_cli_show_unresolvable_flag():
    """Test CLI with --show-unresolvable flag."""
    # Run CLI with flag
    # Verify unresolvable summary is displayed

def test_complex_real_world_file():
    """Test on demo_files/complex_cases.py."""
    # Verify specific unresolvable patterns are caught
    # Check category distribution
```

## Success Metrics

1. **Transparency**: Users can see exactly what percentage of calls were resolved
2. **Categorization**: Unresolvable calls are categorized meaningfully
3. **Examples**: Users get concrete examples of what couldn't be resolved
4. **Backward Compatibility**: Existing code continues to work unchanged
5. **Performance**: No significant performance degradation
6. **Coverage**: Maintains 100% test coverage

## Future Enhancements

This foundation enables future improvements:
- Import resolution (change IMPORTED to resolved)
- Decorator handling (reduce DECORATED category)
- Variable tracking (reduce some UNKNOWN cases)
- Directory-wide analysis with aggregated unresolvable reporting
- Suggestions for making code more analyzable

## Risk Mitigation

1. **Performance**: Limit examples to 5 to avoid memory issues
2. **Complexity**: Keep categorization simple and conservative
3. **User Experience**: Make reporting optional to avoid overwhelming users
4. **Maintenance**: Clear separation between resolution and categorization

## Conclusion

This implementation provides critical transparency about what the tool can and cannot analyze. By explicitly reporting unresolvable calls, we build user trust and help them understand the tool's coverage. The conservative approach aligns with the project philosophy: it's better to say "I don't know" than to guess wrong.

The implementation is modular, testable, and maintains backward compatibility while adding significant value for users who want to understand their analysis coverage.
