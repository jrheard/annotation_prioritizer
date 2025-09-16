# Unresolvable Call Reporting Implementation Plan

**Date:** 2025-09-16
**Implementation Order:** This is step 2 of 3 in the single-file accuracy improvement sequence. Prerequisites: Complete class-detection-improvements-2025-09-16.md first.
**Timeline:** These improvements are for immediate implementation to achieve very accurate single-file analysis. Directory-wide analysis will begin in a few weeks.

## Overview

Currently, the annotation prioritizer silently ignores calls it cannot resolve. This feature will track and report these unresolvable calls to improve transparency and help users understand analysis coverage. This enhancement provides insights into what the analyzer couldn't process, helping users identify potential improvements to their code organization.

## Philosophy

This feature embodies our core principle of conservative resolution: accuracy over completeness. By providing transparency about what the analyzer cannot resolve, we maintain trust with users while avoiding false positives. This aligns with our project philosophy of "very accurate when reading a single file" - we explicitly report what we don't know rather than making uncertain inferences.

## Goals

1. Track all calls that cannot be resolved to known functions
2. Categorize unresolvable calls by type (dynamic, imported, complex qualified, etc.)
3. Provide examples of unresolvable calls in analysis output
4. Maintain backward compatibility with existing API
5. Enable users to assess analysis completeness

## Implementation Steps

### 1. Extend Core Data Models

#### 1.1 New UnresolvableCall Model

Add to `src/annotation_prioritizer/models.py`:

```python
from enum import StrEnum

class UnresolvableCallType(StrEnum):
    """Categories of calls that cannot be resolved."""

    DYNAMIC = "dynamic"  # getattr(obj, 'method')(), obj[key]()
    IMPORTED = "imported"  # module.function(), from module import func
    COMPLEX_QUALIFIED = "complex_qualified"  # obj.attr.method(), chain calls
    UNKNOWN_FUNCTION = "unknown_function"  # calls to functions not in known_functions
    VARIABLE_METHOD = "variable_method"  # obj.method() where obj is a variable
    STAR_IMPORT = "star_import"  # functions from 'from module import *'

@dataclass(frozen=True)
class UnresolvableCall:
    """Information about a call that could not be resolved to a known function."""

    call_text: str  # Raw call as it appears in source (e.g., "obj.method()")
    call_type: UnresolvableCallType  # Category of unresolvable call
    line_number: int  # Line where call appears (1-indexed)
    context: str  # Surrounding context (function/class name where call occurs)
```

#### 1.2 Update CallCountResult Model

Replace the current `CallCount` return pattern with a comprehensive result:

```python
@dataclass(frozen=True)
class CallCountResult:
    """Complete results from call counting analysis."""

    resolved_counts: tuple[CallCount, ...]  # Successfully resolved calls
    unresolvable_calls: tuple[UnresolvableCall, ...]  # Calls that couldn't be resolved
    unresolvable_count: int  # Total number of unresolvable calls
    unresolvable_examples: tuple[UnresolvableCall, ...]  # Sample unresolvable calls (max 5)
```

### 2. Update Call Counter Implementation

#### 2.1 Modify count_function_calls() Signature

In `src/annotation_prioritizer/call_counter.py`:

```python
def count_function_calls(
    file_path: str,
    known_functions: tuple[FunctionInfo, ...]
) -> CallCountResult:
    """Count calls to known functions and track unresolvable calls.

    Returns:
        CallCountResult with both resolved and unresolvable call information
    """
```

#### 2.2 Enhance CallCountVisitor

Add unresolvable call tracking to `CallCountVisitor`:

```python
class CallCountVisitor(ast.NodeVisitor):
    def __init__(self, known_functions: tuple[FunctionInfo, ...]) -> None:
        super().__init__()
        self.call_counts: dict[str, int] = {func.qualified_name: 0 for func in known_functions}
        self.unresolvable_calls: list[UnresolvableCall] = []
        self._scope_stack: list[Scope] = [Scope(kind=ScopeKind.MODULE, name="__module__")]

    def visit_Call(self, node: ast.Call) -> None:
        """Visit function call to count resolved calls and track unresolvable ones."""
        call_name = self._extract_call_name(node)

        if call_name and call_name in self.call_counts:
            self.call_counts[call_name] += 1
        else:
            # Track unresolvable call
            unresolvable_call = self._create_unresolvable_call(node)
            if unresolvable_call:
                self.unresolvable_calls.append(unresolvable_call)

        self.generic_visit(node)

    def _create_unresolvable_call(self, node: ast.Call) -> UnresolvableCall | None:
        """Create UnresolvableCall from an AST Call node."""
        call_text = self._extract_call_text(node)
        call_type = self._classify_unresolvable_call(node)
        context = self._get_current_context()

        if call_text and call_type:
            return UnresolvableCall(
                call_text=call_text,
                call_type=call_type,
                line_number=node.lineno,
                context=context
            )
        return None

    def _extract_call_text(self, node: ast.Call) -> str:
        """Extract readable text representation of the call."""
        # Implementation to convert AST back to source text
        # Handle different call patterns: func(), obj.method(), etc.

    def _classify_unresolvable_call(self, node: ast.Call) -> UnresolvableCallType | None:
        """Classify the type of unresolvable call."""
        func = node.func

        if isinstance(func, ast.Name):
            return UnresolvableCallType.UNKNOWN_FUNCTION

        if isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name):
                if func.value.id in ("self", "cls"):
                    return None  # Should have been resolved
                return UnresolvableCallType.VARIABLE_METHOD
            elif isinstance(func.value, ast.Attribute):
                return UnresolvableCallType.COMPLEX_QUALIFIED
            elif isinstance(func.value, ast.Call):
                return UnresolvableCallType.DYNAMIC

        # getattr(), dynamic calls, etc.
        return UnresolvableCallType.DYNAMIC

    def _get_current_context(self) -> str:
        """Get current scope context for unresolvable call."""
        # Build context from scope stack
        return ".".join(scope.name for scope in self._scope_stack[1:])  # Skip __module__
```

#### 2.3 Update count_function_calls() Implementation

```python
def count_function_calls(
    file_path: str,
    known_functions: tuple[FunctionInfo, ...]
) -> CallCountResult:
    """Count calls to known functions and track unresolvable calls."""
    file_path_obj = Path(file_path)
    if not file_path_obj.exists():
        return CallCountResult(
            resolved_counts=(),
            unresolvable_calls=(),
            unresolvable_count=0,
            unresolvable_examples=()
        )

    try:
        source_code = file_path_obj.read_text(encoding="utf-8")
        tree = ast.parse(source_code, filename=file_path)
    except (OSError, SyntaxError):
        return CallCountResult(
            resolved_counts=(),
            unresolvable_calls=(),
            unresolvable_count=0,
            unresolvable_examples=()
        )

    visitor = CallCountVisitor(known_functions)
    visitor.visit(tree)

    resolved_counts = tuple(
        CallCount(function_qualified_name=name, call_count=count)
        for name, count in visitor.call_counts.items()
    )

    unresolvable_calls = tuple(visitor.unresolvable_calls)
    unresolvable_count = len(unresolvable_calls)

    # Provide examples (max 5) with diverse types
    unresolvable_examples = _select_representative_examples(unresolvable_calls)

    return CallCountResult(
        resolved_counts=resolved_counts,
        unresolvable_calls=unresolvable_calls,
        unresolvable_count=unresolvable_count,
        unresolvable_examples=unresolvable_examples
    )

def _select_representative_examples(
    unresolvable_calls: tuple[UnresolvableCall, ...]
) -> tuple[UnresolvableCall, ...]:
    """Select up to 5 representative examples of unresolvable calls."""
    if len(unresolvable_calls) <= 5:
        return unresolvable_calls

    # Group by type and select examples from each type
    by_type: dict[UnresolvableCallType, list[UnresolvableCall]] = {}
    for call in unresolvable_calls:
        by_type.setdefault(call.call_type, []).append(call)

    examples: list[UnresolvableCall] = []
    for call_type, calls in by_type.items():
        if len(examples) < 5:
            examples.append(calls[0])  # Take first example of each type

    return tuple(examples[:5])
```

### 3. Update Analyzer Integration

#### 3.1 Modify analyzer.py

Update `analyze_file()` to handle new return type:

```python
def analyze_file(file_path: str) -> tuple[FunctionPriority, ...]:
    """Complete analysis pipeline for a single Python file."""
    # 1. Parse function definitions
    function_infos = parse_function_definitions(file_path)

    if not function_infos:
        return ()

    # 2. Count function calls (now returns CallCountResult)
    call_result = count_function_calls(file_path, function_infos)
    call_count_map = {
        cc.function_qualified_name: cc.call_count
        for cc in call_result.resolved_counts
    }

    # 3. Calculate annotation scores and combine into priority rankings
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

    # 4. Sort by priority score (highest first)
    return tuple(sorted(priorities, key=lambda p: p.priority_score, reverse=True))
```

#### 3.2 Add Unresolvable Call Analysis Function

```python
def analyze_file_with_unresolvable_calls(file_path: str) -> tuple[tuple[FunctionPriority, ...], CallCountResult]:
    """Complete analysis including unresolvable call information.

    Returns:
        Tuple of (function_priorities, call_count_result)
    """
    # Similar to analyze_file but returns both priorities and call result
    function_infos = parse_function_definitions(file_path)

    if not function_infos:
        empty_result = CallCountResult(
            resolved_counts=(),
            unresolvable_calls=(),
            unresolvable_count=0,
            unresolvable_examples=()
        )
        return (), empty_result

    call_result = count_function_calls(file_path, function_infos)
    # ... rest of analysis

    return priorities, call_result
```

### 4. Update Output and Display

#### 4.1 Extend output.py

Add functions to display unresolvable call information:

```python
def format_unresolvable_calls_table(call_result: CallCountResult) -> Table:
    """Create Rich table displaying unresolvable calls summary."""
    table = Table(title="Unresolvable Calls Analysis")

    table.add_column("Call Type", style="cyan")
    table.add_column("Count", justify="right", style="magenta")
    table.add_column("Example", style="yellow", no_wrap=True)

    # Group by type for summary
    by_type: dict[UnresolvableCallType, list[UnresolvableCall]] = {}
    for call in call_result.unresolvable_calls:
        by_type.setdefault(call.call_type, []).append(call)

    for call_type, calls in by_type.items():
        example = calls[0].call_text if calls else ""
        table.add_row(
            call_type.value.replace("_", " ").title(),
            str(len(calls)),
            example
        )

    return table

def format_unresolvable_examples_panel(call_result: CallCountResult) -> Panel:
    """Create Rich panel showing detailed examples of unresolvable calls."""
    if not call_result.unresolvable_examples:
        return Panel("No unresolvable calls found", title="Unresolvable Call Examples")

    content = []
    for i, call in enumerate(call_result.unresolvable_examples, 1):
        content.append(f"{i}. {call.call_text} (line {call.line_number})")
        content.append(f"   Type: {call.call_type.value}")
        content.append(f"   Context: {call.context}")
        content.append("")

    return Panel(
        "\n".join(content),
        title=f"Unresolvable Call Examples ({len(call_result.unresolvable_examples)} of {call_result.unresolvable_count})"
    )

def print_unresolvable_calls_summary(console: Console, call_result: CallCountResult) -> None:
    """Print summary of unresolvable calls."""
    if call_result.unresolvable_count == 0:
        console.print("[green]✓ All function calls were successfully resolved.[/green]")
        return

    console.print(f"\n[yellow]⚠️  {call_result.unresolvable_count} unresolvable call(s) found.[/yellow]")

    # Show breakdown by type
    by_type: dict[UnresolvableCallType, int] = {}
    for call in call_result.unresolvable_calls:
        by_type[call.call_type] = by_type.get(call.call_type, 0) + 1

    for call_type, count in sorted(by_type.items()):
        type_name = call_type.value.replace("_", " ").title()
        console.print(f"  • {type_name}: {count}")

def display_results_with_unresolvable_calls(
    console: Console,
    priorities: tuple[FunctionPriority, ...],
    call_result: CallCountResult
) -> None:
    """Display complete analysis results including unresolvable calls."""
    # Display main function priority table
    if priorities:
        table = format_results_table(priorities)
        console.print(table)
        print_summary_stats(console, priorities)
    else:
        console.print("[yellow]No functions found to analyze.[/yellow]")

    # Display unresolvable calls information
    print_unresolvable_calls_summary(console, call_result)

    if call_result.unresolvable_count > 0:
        console.print()

        # Show summary table
        summary_table = format_unresolvable_calls_table(call_result)
        console.print(summary_table)

        # Show detailed examples
        examples_panel = format_unresolvable_examples_panel(call_result)
        console.print(examples_panel)
```

#### 4.2 Update CLI to Support New Display Options

Add optional flag to show unresolvable calls:

```python
# In cli.py
def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(description="Analyze Python files for type annotation priorities")
    parser.add_argument("file_path", help="Python file to analyze")
    parser.add_argument(
        "--show-unresolvable",
        action="store_true",
        help="Include unresolvable call analysis in output"
    )

    args = parser.parse_args()
    console = Console()

    if args.show_unresolvable:
        priorities, call_result = analyze_file_with_unresolvable_calls(args.file_path)
        display_results_with_unresolvable_calls(console, priorities, call_result)
    else:
        priorities = analyze_file(args.file_path)
        display_results(console, priorities)
```

### 5. Comprehensive Test Implementation

#### 5.1 Update test_call_counter.py

Add tests for new CallCountResult return type:

```python
def test_count_function_calls_returns_call_count_result() -> None:
    """Test that count_function_calls returns CallCountResult."""
    code = """
def simple_func():
    pass

def caller():
    simple_func()
    unknown_func()  # Unresolvable
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            FunctionInfo(
                name="simple_func",
                qualified_name="__module__.simple_func",
                parameters=(),
                has_return_annotation=False,
                line_number=2,
                file_path=temp_path,
            ),
        )

        result = count_function_calls(temp_path, known_functions)

        assert isinstance(result, CallCountResult)
        assert len(result.resolved_counts) == 1
        assert result.resolved_counts[0].call_count == 1
        assert result.unresolvable_count == 1
        assert len(result.unresolvable_calls) == 1
        assert result.unresolvable_calls[0].call_text == "unknown_func()"
        assert result.unresolvable_calls[0].call_type == UnresolvableCallType.UNKNOWN_FUNCTION

def test_unresolvable_call_classification() -> None:
    """Test classification of different unresolvable call types."""
    code = """
import math

class TestClass:
    def method(self):
        # Various unresolvable call patterns
        unknown_func()                    # UNKNOWN_FUNCTION
        obj.method()                      # VARIABLE_METHOD
        obj.attr.method()                 # COMPLEX_QUALIFIED
        getattr(self, 'dynamic')()        # DYNAMIC
        math.sqrt(4)                      # IMPORTED (if math not in known_functions)

obj = TestClass()
"""

    with temp_python_file(code) as temp_path:
        known_functions = ()  # No known functions to make all calls unresolvable

        result = count_function_calls(temp_path, known_functions)

        call_types = {call.call_type for call in result.unresolvable_calls}

        assert UnresolvableCallType.UNKNOWN_FUNCTION in call_types
        assert UnresolvableCallType.VARIABLE_METHOD in call_types
        assert UnresolvableCallType.COMPLEX_QUALIFIED in call_types
        assert UnresolvableCallType.DYNAMIC in call_types

def test_unresolvable_examples_selection() -> None:
    """Test that unresolvable examples are properly selected."""
    code = """
def test():
    # Create many unresolvable calls
    unknown1()
    unknown2()
    unknown3()
    unknown4()
    unknown5()
    unknown6()
    unknown7()  # More than 5 to test selection
"""

    with temp_python_file(code) as temp_path:
        result = count_function_calls(temp_path, ())

        assert result.unresolvable_count == 7
        assert len(result.unresolvable_examples) == 5  # Max 5 examples
        assert all(ex in result.unresolvable_calls for ex in result.unresolvable_examples)

def test_unresolvable_call_context() -> None:
    """Test that unresolvable calls capture correct context."""
    code = """
class MyClass:
    def method(self):
        unknown_in_method()

    class NestedClass:
        def nested_method(self):
            unknown_in_nested()

def module_func():
    unknown_in_module_func()
"""

    with temp_python_file(code) as temp_path:
        result = count_function_calls(temp_path, ())

        contexts = {call.context for call in result.unresolvable_calls}
        assert "MyClass.method" in contexts
        assert "MyClass.NestedClass.nested_method" in contexts
        assert "module_func" in contexts
```

#### 5.2 Add test_unresolvable_calls.py

New dedicated test file for unresolvable call functionality:

```python
"""Tests specifically for unresolvable call tracking and reporting."""

import pytest
from annotation_prioritizer.call_counter import count_function_calls
from annotation_prioritizer.models import CallCountResult, UnresolvableCallType
from tests.helpers.temp_files import temp_python_file

def test_empty_file_unresolvable_calls() -> None:
    """Test unresolvable calls tracking with empty file."""
    with temp_python_file("") as temp_path:
        result = count_function_calls(temp_path, ())

        assert result.unresolvable_count == 0
        assert len(result.unresolvable_calls) == 0
        assert len(result.unresolvable_examples) == 0

def test_dynamic_call_detection() -> None:
    """Test detection of dynamic calls like getattr()."""
    code = """
class DynamicExample:
    def method(self):
        method_name = 'other_method'
        getattr(self, method_name)()
        self.__dict__['func']()
        globals()['function']()
"""

    with temp_python_file(code) as temp_path:
        result = count_function_calls(temp_path, ())

        dynamic_calls = [
            call for call in result.unresolvable_calls
            if call.call_type == UnresolvableCallType.DYNAMIC
        ]
        assert len(dynamic_calls) >= 1

def test_imported_function_calls() -> None:
    """Test detection of calls to imported functions."""
    code = """
import os
from pathlib import Path

def use_imports():
    os.path.join('a', 'b')
    Path('/tmp').exists()
"""

    with temp_python_file(code) as temp_path:
        result = count_function_calls(temp_path, ())

        # These should be classified as VARIABLE_METHOD since os and Path are variables
        variable_calls = [
            call for call in result.unresolvable_calls
            if call.call_type == UnresolvableCallType.VARIABLE_METHOD
        ]
        assert len(variable_calls) >= 2

@pytest.mark.parametrize("call_pattern,expected_type", [
    ("unknown_func()", UnresolvableCallType.UNKNOWN_FUNCTION),
    ("obj.method()", UnresolvableCallType.VARIABLE_METHOD),
    ("obj.attr.method()", UnresolvableCallType.COMPLEX_QUALIFIED),
])
def test_call_classification_patterns(call_pattern: str, expected_type: UnresolvableCallType) -> None:
    """Test that different call patterns are classified correctly."""
    code = f"""
def test_function():
    {call_pattern}
"""

    with temp_python_file(code) as temp_path:
        result = count_function_calls(temp_path, ())

        matching_calls = [
            call for call in result.unresolvable_calls
            if call.call_type == expected_type and call_pattern in call.call_text
        ]
        assert len(matching_calls) >= 1

def test_line_numbers_in_unresolvable_calls() -> None:
    """Test that line numbers are correctly captured for unresolvable calls."""
    code = """
def test():
    # Line 3
    unknown1()  # This should be line 4
    # Line 5
    unknown2()  # This should be line 6
"""

    with temp_python_file(code) as temp_path:
        result = count_function_calls(temp_path, ())

        line_numbers = [call.line_number for call in result.unresolvable_calls]
        assert 4 in line_numbers
        assert 6 in line_numbers

def test_call_text_extraction() -> None:
    """Test that call text is properly extracted from AST."""
    code = """
def test():
    simple_call()
    obj.method_call(arg1, arg2)
    complex.chain.call()
"""

    with temp_python_file(code) as temp_path:
        result = count_function_calls(temp_path, ())

        call_texts = [call.call_text for call in result.unresolvable_calls]

        # Should contain recognizable call patterns
        assert any("simple_call" in text for text in call_texts)
        assert any("method_call" in text for text in call_texts)
        assert any("chain" in text for text in call_texts)
```

#### 5.3 Update Integration Tests

Extend `test_end_to_end.py` to include unresolvable call scenarios:

```python
def test_end_to_end_with_unresolvable_calls() -> None:
    """Test complete analysis pipeline including unresolvable call tracking."""
    code = """
def annotated_func(x: int) -> int:
    return x * 2

def unannotated_func(y):
    result = annotated_func(y)
    unknown_function(result)  # Unresolvable call
    return result

def main():
    unannotated_func(5)
"""

    with temp_python_file(code) as temp_path:
        priorities, call_result = analyze_file_with_unresolvable_calls(temp_path)

        # Verify function priorities work as expected
        assert len(priorities) == 3

        # Verify unresolvable calls are tracked
        assert call_result.unresolvable_count == 1
        assert call_result.unresolvable_calls[0].call_text == "unknown_function(result)"
        assert call_result.unresolvable_calls[0].call_type == UnresolvableCallType.UNKNOWN_FUNCTION
        assert call_result.unresolvable_calls[0].context == "unannotated_func"
```

#### 5.4 Update Output Tests

Add tests for new display functions in `test_output.py`:

```python
def test_format_unresolvable_calls_table() -> None:
    """Test formatting of unresolvable calls summary table."""
    from annotation_prioritizer.models import CallCountResult, UnresolvableCall, UnresolvableCallType
    from annotation_prioritizer.output import format_unresolvable_calls_table

    unresolvable_calls = (
        UnresolvableCall(
            call_text="unknown_func()",
            call_type=UnresolvableCallType.UNKNOWN_FUNCTION,
            line_number=5,
            context="test_function"
        ),
        UnresolvableCall(
            call_text="obj.method()",
            call_type=UnresolvableCallType.VARIABLE_METHOD,
            line_number=10,
            context="another_function"
        ),
    )

    call_result = CallCountResult(
        resolved_counts=(),
        unresolvable_calls=unresolvable_calls,
        unresolvable_count=2,
        unresolvable_examples=unresolvable_calls
    )

    table = format_unresolvable_calls_table(call_result)

    assert table.title == "Unresolvable Calls Analysis"
    assert len(table.columns) == 3

def test_print_unresolvable_calls_summary_empty() -> None:
    """Test summary output when no unresolvable calls exist."""
    from annotation_prioritizer.models import CallCountResult
    from annotation_prioritizer.output import print_unresolvable_calls_summary
    from tests.helpers.console import capture_console_output

    call_result = CallCountResult(
        resolved_counts=(),
        unresolvable_calls=(),
        unresolvable_count=0,
        unresolvable_examples=()
    )

    output = capture_console_output(lambda console: print_unresolvable_calls_summary(console, call_result))
    assert "All function calls were successfully resolved" in output

def test_print_unresolvable_calls_summary_with_calls() -> None:
    """Test summary output when unresolvable calls exist."""
    from annotation_prioritizer.models import CallCountResult, UnresolvableCall, UnresolvableCallType
    from annotation_prioritizer.output import print_unresolvable_calls_summary
    from tests.helpers.console import capture_console_output

    unresolvable_calls = (
        UnresolvableCall(
            call_text="unknown_func()",
            call_type=UnresolvableCallType.UNKNOWN_FUNCTION,
            line_number=5,
            context="test_function"
        ),
    )

    call_result = CallCountResult(
        resolved_counts=(),
        unresolvable_calls=unresolvable_calls,
        unresolvable_count=1,
        unresolvable_examples=unresolvable_calls
    )

    output = capture_console_output(lambda console: print_unresolvable_calls_summary(console, call_result))
    assert "1 unresolvable call(s) found" in output
    assert "Unknown Function: 1" in output
```

### 6. Data Flow Examples

#### 6.1 Before (Current Implementation)

```python
# Input code
def my_function():
    known_func()      # Counted
    unknown_func()    # Silently ignored
    obj.method()      # Silently ignored

# Current output
call_counts = count_function_calls(file_path, known_functions)
# Returns: (CallCount(function_qualified_name="__module__.known_func", call_count=1),)
# Information about unknown_func() and obj.method() is lost
```

#### 6.2 After (New Implementation)

```python
# Input code
def my_function():
    known_func()      # Counted in resolved_counts
    unknown_func()    # Tracked in unresolvable_calls
    obj.method()      # Tracked in unresolvable_calls

# New output
call_result = count_function_calls(file_path, known_functions)
# Returns: CallCountResult(
#   resolved_counts=(CallCount(function_qualified_name="__module__.known_func", call_count=1),),
#   unresolvable_calls=(
#     UnresolvableCall(call_text="unknown_func()", call_type=UNKNOWN_FUNCTION, line_number=3, context="my_function"),
#     UnresolvableCall(call_text="obj.method()", call_type=VARIABLE_METHOD, line_number=4, context="my_function")
#   ),
#   unresolvable_count=2,
#   unresolvable_examples=(...)
# )
```

### 7. Performance Considerations

1. **Memory Usage**: Storing all unresolvable calls may increase memory usage. Limit examples to 5 per type.
2. **Processing Time**: AST-to-text conversion adds overhead. Implement efficient text extraction.
3. **Large Files**: Consider limits on total unresolvable calls tracked (e.g., max 1000).

### 8. Backward Compatibility

1. **Existing API**: Keep original `analyze_file()` function unchanged.
2. **New API**: Add `analyze_file_with_unresolvable_calls()` for extended functionality.
3. **CLI Options**: Make unresolvable call display optional via `--show-unresolvable` flag.

### 9. Future Enhancements

1. **Confidence Scores**: Add confidence levels for unresolvable call classification.
2. **Import Resolution**: Enhance to resolve some imported function calls.
3. **Call Graph**: Build comprehensive call graph including unresolvable calls.
4. **IDE Integration**: Export unresolvable calls in IDE-friendly formats.

## Testing Strategy

1. **Unit Tests**: Comprehensive coverage of new models and call classification.
2. **Integration Tests**: End-to-end testing with various code patterns.
3. **Edge Cases**: Complex nested structures, dynamic calls, edge cases.
4. **Performance Tests**: Ensure acceptable performance with large files.
5. **Backward Compatibility**: Verify existing functionality remains unchanged.

## Success Criteria

1. All unresolvable calls are properly categorized and tracked
2. Examples provide meaningful insights into analysis coverage
3. Backward compatibility maintained for existing API
4. Test coverage remains at 100%
5. Performance impact is minimal (< 10% overhead)
6. Output is clear and actionable for users

## Implementation Order

1. Extend data models (UnresolvableCall, CallCountResult)
2. Update CallCountVisitor to track unresolvable calls
3. Modify count_function_calls() signature and implementation
4. Update analyzer.py integration
5. Add output formatting functions
6. Update CLI with new options
7. Implement comprehensive tests
8. Update documentation and examples

This implementation will provide users with complete visibility into the analysis process, helping them understand both what was successfully analyzed and what patterns the tool couldn't resolve, ultimately improving code organization and analysis effectiveness.
