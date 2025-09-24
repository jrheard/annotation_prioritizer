# AST Parsing Refactor Implementation Plan

## Overview

This plan refactors the AST parsing architecture to eliminate duplicate file reading and parsing between `parse_function_definitions()` and `count_function_calls()`. Currently, both functions independently read the same file and parse it to an AST. After this refactor, parsing will happen once at the orchestration level with all dependencies (AST, registries, source code) passed down to the functions that need them.

## Motivation

1. **Performance**: Eliminate duplicate I/O and AST parsing operations
2. **Enable Features**: Make class registry available during function parsing (needed for class instantiation tracking)
3. **Clean Architecture**: Separate concerns - parsing vs analysis
4. **Explicit Dependencies**: Make data dependencies visible in function signatures

## Design Decisions

### File Organization
We'll add the new parsing utility directly to the `ast_visitors/` directory alongside the existing visitor implementations. This keeps all AST-related code together in one place.

### Function Signature Changes
Functions will receive their dependencies rather than creating them:
- Old: Functions take file path, do their own parsing/registry building
- New: Functions receive pre-parsed AST, pre-built registries, and source code

### Path Standardization
We'll standardize on `Path` objects instead of strings for file paths throughout the refactored code.

### Source Code Passing
`parse_ast_from_file()` will return both the AST and source code string, since `CallCountVisitor` needs the source for error context. This avoids reading the file multiple times.

## Implementation Steps

### Step 1: Create parse_ast module with parsing function ✅ COMPLETED

Create `src/annotation_prioritizer/ast_visitors/parse_ast.py`:

```python
"""Common AST parsing utilities."""

import ast
from pathlib import Path


def parse_ast_from_file(file_path: Path) -> tuple[ast.Module, str] | None:
    """Parse a Python file into an AST and return source code.

    Args:
        file_path: Path to the Python source file

    Returns:
        Tuple of (AST module, source code) on success, None on failure
        (file not found or syntax error)
    """
    if not file_path.exists():
        return None

    try:
        source_code = file_path.read_text(encoding="utf-8")
        tree = ast.parse(source_code, filename=str(file_path))
        return (tree, source_code)
    except (OSError, SyntaxError):
        return None
```

Write tests for this function covering:
- Successful parsing
- File not found
- Syntax error in file
- Empty file

**Commit**: `feat: add parse_ast_from_file utility function` ✅ COMPLETED

**Implementation notes**:
- Updated module docstring to be more focused on constraining scope per user feedback
- Used bare test functions instead of test classes per test guidelines
- Fixed all linting issues including using Path.chmod() instead of os.chmod()

### Step 2: Update parse_function_definitions and its callers ✅ COMPLETED

First, update the function signature in `src/annotation_prioritizer/ast_visitors/function_parser.py`:

```python
from pathlib import Path
from annotation_prioritizer.ast_visitors.class_discovery import ClassRegistry

def parse_function_definitions(
    tree: ast.Module,
    file_path: Path,
    class_registry: ClassRegistry,
) -> tuple[FunctionInfo, ...]:
    """Extract all function definitions from a parsed AST.

    Args:
        tree: Parsed AST module
        file_path: Path to the source file (for FunctionInfo objects)
        class_registry: Registry of known classes

    Returns:
        Tuple of FunctionInfo objects
    """
    visitor = FunctionDefinitionVisitor(str(file_path))  # Convert Path to str for now
    visitor.visit(tree)
    return tuple(visitor.functions)
```

Remove the old file reading/parsing logic from this function.

Update `analyzer.py` to use the new signature:

```python
from pathlib import Path
from .ast_visitors.parse_ast import parse_ast_from_file
from .ast_visitors.class_discovery import build_class_registry
from .ast_visitors.variable_discovery import build_variable_registry

def analyze_file(file_path: str) -> AnalysisResult:
    """Complete analysis pipeline for a single Python file."""
    file_path_obj = Path(file_path)

    # Parse once
    parse_result = parse_ast_from_file(file_path_obj)
    if not parse_result:
        return AnalysisResult(priorities=(), unresolvable_calls=())

    tree, source_code = parse_result

    # Build registries
    class_registry = build_class_registry(tree)

    # 1. Parse function definitions with class registry
    function_infos = parse_function_definitions(
        tree, file_path_obj, class_registry
    )

    if not function_infos:
        return AnalysisResult(priorities=(), unresolvable_calls=())

    # Build variable registry (needs class registry)
    variable_registry = build_variable_registry(tree, class_registry)

    # 2. Count function calls (temporarily still using old signature)
    resolved_counts, unresolvable_calls = count_function_calls(
        file_path, function_infos  # Will update this in next step
    )

    # ... rest remains the same
```

Update all tests that call `parse_function_definitions()` to:
1. Parse the file first using `parse_ast_from_file()`
2. Build class registry
3. Pass all required parameters

This includes updating tests in:
- `tests/integration/test_function_parser.py`
- Any other test files that directly call this function

**Commit**: `refactor: update parse_function_definitions to accept AST and registries` ✅ COMPLETED

**Implementation notes**:
- Updated function signature to accept tree, file_path, and class_registry
- Modified analyzer.py to parse file once and pass AST/registries
- Created shared test helper `parse_functions_from_file` in tests/helpers/function_parsing.py to avoid duplication
- Added test for nonexistent file case in analyze_file to maintain 100% coverage
- Fixed linting issues (unused variables, unused parameters)

### Step 3: Update count_function_calls and complete analyzer.py ✅ COMPLETED

Update `src/annotation_prioritizer/ast_visitors/call_counter.py`:

```python
from pathlib import Path

def count_function_calls(
    tree: ast.Module,
    known_functions: tuple[FunctionInfo, ...],
    class_registry: ClassRegistry,
    variable_registry: VariableRegistry,
    source_code: str,
) -> tuple[tuple[CallCount, ...], tuple[UnresolvableCall, ...]]:
    """Count calls to known functions in the AST.

    Args:
        tree: Parsed AST module
        known_functions: Functions to count calls for
        class_registry: Registry of known classes
        variable_registry: Registry of variable type information
        source_code: Source code for error context

    Returns:
        Tuple of (resolved call counts, unresolvable calls)
    """
    visitor = CallCountVisitor(
        known_functions, class_registry, source_code, variable_registry
    )
    visitor.visit(tree)

    resolved = tuple(
        CallCount(function_qualified_name=name, call_count=count)
        for name, count in visitor.call_counts.items()
    )

    return (resolved, visitor.get_unresolvable_calls())
```

Remove the file reading, parsing, and registry building logic.

Complete the analyzer.py update:

```python
def analyze_file(file_path: str) -> AnalysisResult:
    """Complete analysis pipeline for a single Python file."""
    file_path_obj = Path(file_path)

    # Parse once
    parse_result = parse_ast_from_file(file_path_obj)
    if not parse_result:
        return AnalysisResult(priorities=(), unresolvable_calls=())

    tree, source_code = parse_result

    # Build all registries upfront
    class_registry = build_class_registry(tree)
    variable_registry = build_variable_registry(tree, class_registry)

    # 1. Parse function definitions
    function_infos = parse_function_definitions(
        tree, file_path_obj, class_registry
    )

    if not function_infos:
        return AnalysisResult(priorities=(), unresolvable_calls=())

    # 2. Count function calls with all dependencies
    resolved_counts, unresolvable_calls = count_function_calls(
        tree, function_infos, class_registry, variable_registry, source_code
    )

    # ... rest remains the same
```

Update all tests that call `count_function_calls()` to:
1. Parse the file first
2. Build both registries
3. Pass all required parameters

This includes updating tests in:
- `tests/integration/test_call_counter.py`
- Any helper functions in `tests/helpers/` that use this function

**Commit**: `refactor: update count_function_calls to accept AST and registries` ✅ COMPLETED

**Implementation notes**:
- Updated function signature to accept tree, known_functions, class_registry, variable_registry, and source_code
- Removed all file reading, parsing, and registry building logic from count_function_calls
- Updated analyzer.py to import and build variable_registry
- Updated analyzer.py to store source_code from parse result and pass all dependencies
- Created count_calls_from_file helper function in tests/helpers/function_parsing.py for test simplification
- Updated all test files to use the new helper function instead of calling count_function_calls directly
- All tests pass with 100% coverage, all linting and type checking passes

### Step 4: Update file path types throughout ✅ COMPLETED

**Note**: Initial investigation showed that `FunctionInfo.file_path` was used throughout the codebase (65+ occurrences in tests alone). Despite the complexity, the Path standardization was successfully implemented.

Completed Path standardization:
1. Updated `FunctionDefinitionVisitor` constructor to accept `Path` ✅
2. Updated `FunctionInfo.file_path` from `str` to `Path` ✅
3. Updated all test files that construct `FunctionInfo` objects ✅
4. Verified CLI and output formatting still work correctly ✅

**Commit**: `refactor: standardize on Path objects for file paths` ✅ COMPLETED

**Implementation notes**:
- Updated FunctionInfo model to use Path type for file_path field
- Modified FunctionDefinitionVisitor to accept and store Path objects
- Updated test factories to accept Path objects (with None default to avoid pyright issues)
- Modified temp_python_file helper to yield Path objects instead of strings
- Updated parse_functions_from_file and count_calls_from_file helpers to accept Path
- Fixed all test files to use Path objects when calling factory functions
- All tests pass with 100% coverage, all linting and type checking passes

### Step 5: Update documentation and remove obsolete comments

Update docstrings and comments:
1. Remove "two-stage analysis" references from `call_counter.py`
2. Update module docstrings to reflect new responsibilities
3. Ensure all function docstrings accurately describe parameters and behavior
4. Remove any comments about building registries from inside the functions

Key places to update:
- Module docstring in `call_counter.py` (remove Stage 1/Stage 2 description)
- Function docstrings for both modified functions
- Any inline comments referring to the old architecture

**Commit**: `docs: update documentation to reflect new AST parsing architecture`

## Testing Strategy

Each step must maintain 100% test coverage and pass all pre-commit hooks:
- Unit tests for new `parse_ast_from_file()` function
- Update existing tests to provide required dependencies
- Integration tests should continue to work through `analyze_file()`
- All tests must pass before each commit

## Verification

After implementation:
1. Run the full test suite with coverage: `pytest --cov=src --cov-report=term-missing --cov-fail-under=100`
2. Verify pre-commit hooks pass: `pre-commit run --all-files`
3. Test the CLI on demo files to ensure end-to-end functionality
4. Verify no duplicate file I/O by reviewing the code paths

## Benefits Realized

Upon completion:
- Single file read and AST parse per analysis
- Class registry available during function parsing (enables class instantiation tracking)
- Cleaner separation of concerns
- More testable code with explicit dependencies
- Foundation laid for future enhancements

## Future Work Enabled

This refactor directly enables:
- Class instantiation tracking (class registry now available during function parsing)
- Potential caching of parsed ASTs for multiple analyses
- Easier testing with mock ASTs and registries
- Possibility of analyzing pre-parsed ASTs from other sources
