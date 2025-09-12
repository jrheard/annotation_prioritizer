# Test Helpers Refactoring Implementation Plan

**Date**: 2025-09-12
**Priority**: Medium-High
**Estimated Effort**: 2-3 hours
**Impact**: Reduce test code duplication by 36+ instances, ~250 lines of code

## Overview

Analysis of the test suite revealed significant code duplication across 6 test files with repetitive patterns for temporary file management and console output capture. This plan outlines the creation of 2 targeted helper functions to eliminate the most impactful duplication and improve test maintainability.

### Current State Analysis

**Files Analyzed:**
- `tests/unit/test_parser.py` (341 lines)
- `tests/unit/test_call_counter.py` (456 lines)
- `tests/unit/test_output.py` (235 lines)
- `tests/unit/test_cli.py` (194 lines)
- `tests/unit/test_scoring.py` (294 lines)
- `tests/integration/test_end_to_end.py` (175 lines)

**Key Finding**: No existing test helpers directory found - all helper functions need to be created from scratch.

## Implementation Steps

### Step 1: Create Test Helpers Directory Structure

Create the following directory structure:

```
tests/
├── helpers/
│   ├── __init__.py
│   ├── temp_files.py      # Temporary file management
│   └── console.py         # Console output capture
├── unit/
├── integration/
└── conftest.py
```

**Implementation:**
1. Create `tests/helpers/` directory
2. Create empty `__init__.py` for Python package detection
3. Create the two helper modules as detailed below

### Step 2: Implement Temporary File Helper (Highest Priority)

**File**: `tests/helpers/temp_files.py`

**Affected Files**:
- `test_parser.py`: Lines 12-19, 30-37, 47-65, 75-90, 100-113, 123-138, 148-163, 182-205, 220-233, 247-262, 272-285, 295-307, 327-340
- `test_call_counter.py`: Lines 27-69, 92-134, 152-177, 190-221, 236-258, 274-302, 322-347, 373-408, 420-438, 442-455
- `test_end_to_end.py`: Lines 35-38, 99-101, 135-137

**Current Duplication Pattern:**
```python
with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
    f.write(source)
    f.flush()

    result = parse_function_definitions(f.name)
    # ... test logic ...

    Path(f.name).unlink()
```

**Helper Implementation:**
```python
"""Temporary file utilities for testing."""

import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


@contextmanager
def temp_python_file(content: str) -> Iterator[str]:
    """Create a temporary Python file with the given content.

    Args:
        content: Python source code to write to the file

    Yields:
        str: Path to the temporary file

    Example:
        with temp_python_file('def test(): pass') as path:
            result = parse_function_definitions(path)
            assert len(result) == 1
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(content)
        f.flush()
        temp_path = f.name

    try:
        yield temp_path
    finally:
        Path(temp_path).unlink()


```

**Migration Example:**
```python
# BEFORE (13 lines)
def test_parse_simple_function_no_annotations() -> None:
    """Test parsing a simple function without annotations."""
    source = """
def simple_function(a, b):
    return a + b
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(source)
        f.flush()

        result = parse_function_definitions(f.name)
        assert len(result) == 1
        # ... more assertions ...

        Path(f.name).unlink()

# AFTER (8 lines)
def test_parse_simple_function_no_annotations() -> None:
    """Test parsing a simple function without annotations."""
    source = """
def simple_function(a, b):
    return a + b
"""

    with temp_python_file(source) as path:
        result = parse_function_definitions(path)
        assert len(result) == 1
        # ... more assertions ...
```

### Step 3: Implement Console Output Capture Helper

**File**: `tests/helpers/console.py`

**Affected Files**:
- `test_output.py`: Lines 99-100, 129-130, 181-182, 195-196, 225-226
- `test_cli.py`: Lines 33-34, 51-52, 100-101, 144-145, 162-163, 182-183

**Current Duplication Pattern:**
```python
output = StringIO()
console = Console(file=output, force_terminal=False, width=80)
```

**Helper Implementation:**
```python
"""Console testing utilities."""

from contextlib import contextmanager
from io import StringIO
from typing import Iterator

from rich.console import Console


@contextmanager
def capture_console_output(width: int = 80, force_terminal: bool = False) -> Iterator[tuple[Console, StringIO]]:
    """Create a Console instance with captured output.

    Args:
        width: Console width in characters
        force_terminal: Whether to force terminal mode

    Yields:
        tuple[Console, StringIO]: Console instance and output buffer

    Example:
        with capture_console_output() as (console, output):
            display_results(console, data)
            output_str = output.getvalue()
            assert "Expected text" in output_str
    """
    output = StringIO()
    console = Console(file=output, force_terminal=force_terminal, width=width)
    yield console, output


def assert_console_contains(output: StringIO, *expected_texts: str) -> None:
    """Assert that console output contains all expected text fragments.

    Args:
        output: StringIO buffer from capture_console_output
        expected_texts: Text fragments that should be present

    Example:
        with capture_console_output() as (console, output):
            print_summary_stats(console, data)
            assert_console_contains(output, "Total functions", "High priority")
    """
    output_str = output.getvalue()
    for text in expected_texts:
        assert text in output_str, f"Expected '{text}' not found in output: {output_str!r}"
```

**Migration Example:**
```python
# BEFORE (8 lines)
def test_print_summary_stats_empty() -> None:
    """Test printing summary stats for empty results."""
    output = StringIO()
    console = Console(file=output, force_terminal=False, width=80)

    print_summary_stats(console, ())

    output_str = output.getvalue()
    assert "No functions found to analyze." in output_str

# AFTER (5 lines)
def test_print_summary_stats_empty() -> None:
    """Test printing summary stats for empty results."""
    with capture_console_output() as (console, output):
        print_summary_stats(console, ())
        assert_console_contains(output, "No functions found to analyze.")
```



## Migration Strategy

### Phase 1: Create Helper Infrastructure ✅ **COMPLETED**
1. ✅ Create `tests/helpers/` directory and `__init__.py`
2. ✅ Implement the two helper modules with comprehensive docstrings
3. ✅ Add imports to `tests/helpers/__init__.py` for convenience

**Status**: Infrastructure complete - all helper modules created with proper linting and type checking

### Phase 2: Migrate High-Impact Files (1.5 hours)
1. ✅ **Priority 1**: `test_parser.py` - 13 instances of temp file pattern **COMPLETED** (68 lines removed, 341→273 lines)
2. ✅ **Priority 2**: `test_call_counter.py` - 10 instances of temp file pattern **COMPLETED** (61 lines removed, 456→395 lines)
3. ✅ **Priority 3**: `test_output.py` - 5 instances of console pattern **COMPLETED** (26 lines removed, 235→209 lines)
4. ✅ **Priority 4**: `test_cli.py` - 6 instances of console pattern **COMPLETED** (28 lines removed, 194→166 lines)

### Phase 3: Migrate Remaining Files (15 minutes)
1. `test_end_to_end.py` - 3 instances of temp file pattern

### Phase 4: Verification and Cleanup (15 minutes)
1. Run full test suite to ensure no regressions
2. Update imports in test files to use helper functions
3. Clean up any unused imports

## Testing Strategy

**Before Migration:**
```bash
pytest --cov=src --cov-report=term-missing --cov-fail-under=100
```

**During Migration (per file):**
```bash
pytest tests/unit/test_parser.py -v
pytest tests/unit/test_call_counter.py -v
pytest tests/unit/test_output.py -v
pytest tests/unit/test_cli.py -v
pytest tests/integration/test_end_to_end.py -v
```

**After Migration:**
```bash
pytest --cov=src --cov-report=term-missing --cov-fail-under=100
ruff check tests/
pyright tests/
```

## Dependencies and Assumptions

### Required Imports
Helper modules will need these imports:
- `tempfile`, `pathlib.Path` - for temp file management
- `contextlib.contextmanager` - for context managers
- `io.StringIO` - for output capture
- `rich.console.Console` - for console testing

### Assumptions
1. **No Breaking Changes**: All helper functions maintain the same interface patterns as current code
2. **Test Coverage**: Current test coverage of 100% must be maintained
3. **Python Version**: Compatible with Python 3.13+ as specified in project config
4. **Import Strategy**: Helper functions will be imported directly, not through conftest.py fixtures
5. **Error Handling**: Helper functions include appropriate error handling and cleanup

### File Structure After Implementation

```
tests/
├── helpers/
│   ├── __init__.py              # Convenience imports
│   ├── temp_files.py            # temp_python_file context manager
│   └── console.py               # capture_console_output context manager
├── unit/
│   ├── test_parser.py           # ✅ **COMPLETED** - Refactored (13 instances, 68 lines removed)
│   ├── test_call_counter.py     # ✅ **COMPLETED** - Refactored (10 instances, 61 lines removed)
│   ├── test_output.py           # ✅ **COMPLETED** - Refactored (5 instances, 26 lines removed)
│   ├── test_cli.py              # ✅ **COMPLETED** - Refactored (6 instances, 28 lines removed)
│   └── test_scoring.py          # No changes (edge case testing)
├── integration/
│   └── test_end_to_end.py       # ✓ Refactored (3 instances)
└── conftest.py                  # No changes needed
```

## Success Metrics

- **Code Reduction**: 34+ instances of duplication eliminated (34 of 37 total completed)
- **Line Count**: ~183+ lines of test code removed (183 of ~250 total completed)
- **Maintainability**: Consistent patterns for file management and console testing
- **Test Coverage**: Maintain 100% coverage requirement
- **Performance**: Test execution time unchanged or improved
- **Documentation**: All helpers fully documented with examples

## Risk Mitigation

1. **Regression Risk**: Migrate one file at a time, run tests after each
2. **Import Issues**: Test helper imports before migrating files
3. **Context Manager Issues**: Verify proper resource cleanup in all helpers
4. **Path Issues**: Test temp file helpers on different platforms if needed

## Future Enhancements

After implementation, consider these additional improvements:
1. **Performance Helpers**: If test execution becomes slow, add performance measurement utilities
2. **Assertion Helpers**: Create domain-specific assertion functions for common test patterns
3. **Fixture Integration**: Consider converting some helpers to pytest fixtures if beneficial
4. **Test Data Files**: For complex test scenarios, consider external test data files with helper loaders

---

**Implementation Ready**: This plan provides all necessary details for implementation. Estimated completion time: 2-3 hours for a developer familiar with the codebase.
