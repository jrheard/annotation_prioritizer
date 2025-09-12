# Initial Implementation Plan - Type Annotation Priority Analyzer

## Overview

This document outlines the detailed implementation plan for the first 5 commits of the type annotation priority analyzer project. The goal is to build a working analyzer for simple cases (same-module functions only) while avoiding complex static analysis challenges like import resolution and inheritance.

## Implementation Progress

- ✅ **Commit 1**: Core Data Models - COMPLETED
- ✅ **Commit 2**: Basic AST Parsing for Function Definitions - COMPLETED
- ✅ **Commit 3**: Weighted Component Annotation Scoring - COMPLETED
- ⏳ **Commit 4**: Simple Call Counting - PENDING
- ⏳ **Commit 5**: CLI Integration and Output - PENDING

## Current Project State

- **Skeleton**: Basic project structure with `src/annotation_prioritizer/` package
- **CLI**: Placeholder "Hello World" in `src/annotation_prioritizer/cli.py:main`
- **Tooling**: Fully configured with uv, ruff, pyright (strict), pytest, pre-commit
- **Standards**: 100% test coverage, functional programming style, frozen dataclasses
- **Dependencies**: Runtime (rich), dev (pytest, coverage, pre-commit)

## Strategic Approach

**Scope Limitations for Initial Implementation:**
- Same-module function calls only (no imports)
- No inheritance or method resolution order
- No complex scope resolution (LEGB rules)
- Direct function calls only (no dynamic calls via getattr, etc.)

**Key Design Principles:**
1. Pure functions wherever possible
2. Frozen dataclasses for all structured data
3. No inheritance (use bare functions)
4. AST-based static analysis only (no runtime instrumentation)

## Detailed Commit Plan

### Commit 1: Core Data Models

**Goal**: Define the fundamental data structures that will flow through the analysis pipeline.

**Files to Create:**
- `src/annotation_prioritizer/models.py`

**Data Structures Needed:**

```python
@dataclass(frozen=True)
class ParameterInfo:
    name: str
    has_annotation: bool
    is_variadic: bool  # *args
    is_keyword: bool   # **kwargs

@dataclass(frozen=True)
class FunctionInfo:
    name: str
    qualified_name: str  # e.g., "module.ClassName.method_name"
    parameters: tuple[ParameterInfo, ...]
    has_return_annotation: bool
    line_number: int
    file_path: str

@dataclass(frozen=True)
class CallCount:
    function_qualified_name: str
    call_count: int

@dataclass(frozen=True)
class AnnotationScore:
    function_qualified_name: str
    parameter_score: float  # 0.0 to 1.0
    return_score: float     # 0.0 to 1.0
    total_score: float      # weighted combination

@dataclass(frozen=True)
class FunctionPriority:
    function_info: FunctionInfo
    annotation_score: AnnotationScore
    call_count: int
    priority_score: float  # combined metric for ranking
```

**Key Considerations:**
- Use `qualified_name` as the unique identifier for functions
- Handle edge cases: functions with no parameters, *args, **kwargs
- Keep all data immutable with frozen dataclasses

**No Unit Tests**: These are pure data containers with no business logic.

### Commit 2: Basic AST Parsing for Function Definitions

**Goal**: Extract function and method definitions from Python source files using AST parsing.

**Files to Create:**
- `src/annotation_prioritizer/parser.py`
- `tests/unit/test_parser.py`

**Core Functionality:**

```python
def parse_function_definitions(file_path: str) -> tuple[FunctionInfo, ...]:
    """Extract all function definitions from a Python file."""
    # Use ast.parse() and ast.NodeVisitor
    # Handle both module-level functions and class methods
    # Create qualified names (e.g., "ClassName.method_name")

class FunctionDefinitionVisitor(ast.NodeVisitor):
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        # Extract function name, parameters, return annotation
        # Determine if inside a class (for qualified naming)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        # Handle async functions similarly
```

**Implementation Details:**
- Use `ast.parse()` to get AST from source code
- Walk AST with custom `ast.NodeVisitor` subclass
- Track class context for method qualified names
- Extract parameter annotations by checking `arg.annotation`
- Extract return annotations from `returns` attribute
- Handle special parameters (*args, **kwargs) correctly

**Test Cases to Cover:**
- Module-level functions (annotated and unannotated)
- Class methods (instance, class, static methods)
- Functions with various parameter combinations
- Functions with/without return annotations
- Mixed annotation scenarios

### Commit 3: Weighted Component Annotation Scoring

**Goal**: Implement the weighted scoring system for annotation completeness.

**Files to Create:**
- `src/annotation_prioritizer/scoring.py`
- `tests/unit/test_scoring.py`

**Scoring Algorithm (Option 2 - Weighted Components):**

```python
def calculate_annotation_score(function_info: FunctionInfo) -> AnnotationScore:
    """Calculate annotation completeness score with weighted components."""
    # Parameters: each parameter gets equal weight within parameter portion
    # Return type: gets fixed weight (e.g., 25% of total score)
    # Parameter portion: remaining weight (e.g., 75% of total score)

RETURN_TYPE_WEIGHT = 0.25
PARAMETERS_WEIGHT = 0.75

def calculate_parameter_score(parameters: tuple[ParameterInfo, ...]) -> float:
    """Calculate 0.0-1.0 score for parameter annotations."""
    if not parameters:
        return 1.0  # No parameters = fully annotated

    annotated_count = sum(1 for p in parameters if p.has_annotation)
    return annotated_count / len(parameters)

def calculate_return_score(has_return_annotation: bool) -> float:
    """Calculate 0.0-1.0 score for return annotation."""
    return 1.0 if has_return_annotation else 0.0
```

**Edge Cases to Handle:**
- Functions with no parameters (100% parameter score)
- Functions with only *args/**kwargs
- Functions with mix of regular and variadic parameters
- Async functions
- Property methods, setters, etc.

**Test Cases:**
- Various parameter/return annotation combinations
- Edge cases with no parameters
- Functions with *args, **kwargs
- Score calculation accuracy

### Commit 4: Simple Call Counting

**Goal**: Count function calls within the same module, building call frequency data.

**Files to Create:**
- `src/annotation_prioritizer/call_counter.py`
- `tests/unit/test_call_counter.py`

**Core Functionality:**

```python
def count_function_calls(file_path: str, known_functions: tuple[FunctionInfo, ...]) -> tuple[CallCount, ...]:
    """Count calls to known functions within the same file."""
    # Use AST to find all function calls
    # Match call names to known function qualified names
    # Return call counts for each function

class CallCountVisitor(ast.NodeVisitor):
    def visit_Call(self, node: ast.Call) -> None:
        # Handle direct function calls: func_name()
        # Handle method calls: obj.method_name()
        # Handle qualified calls: ClassName.static_method()
```

**Implementation Strategy:**
- Parse file AST to find `ast.Call` nodes
- For each call, determine target function name
- Match against known functions from same module
- Simple name matching (no complex resolution)
- Track class context for method call attribution

**Call Types to Handle:**
- Direct function calls: `function_name()`
- Method calls on `self`: `self.method_name()`
- Static/class method calls: `ClassName.method_name()`
- Calls with qualified names within same module

**Calls to Skip (Out of Scope):**
- Imported function calls
- Dynamic calls via `getattr`
- Calls where target cannot be statically determined

**Test Cases:**
- Various call patterns within same module
- Method calls vs function calls
- Multiple calls to same function
- Calls to unknown/external functions (should be ignored)

### Commit 5: CLI Integration and Output

**Goal**: Replace placeholder CLI with actual analyzer, add command-line interface, implement Rich output.

**Files to Modify:**
- `src/annotation_prioritizer/cli.py` (major rewrite)
- `tests/unit/test_cli.py` (update)

**Files to Create:**
- `src/annotation_prioritizer/analyzer.py` (main analysis orchestrator)
- `src/annotation_prioritizer/output.py` (Rich formatting)
- `tests/integration/test_end_to_end.py`

**CLI Interface Design:**

```python
def main() -> None:
    """Main CLI entry point."""
    # Parse command line arguments
    # Run analysis on target files/directories
    # Display results using Rich

# Command line args:
# --target PATH (file or directory to analyze)
# --min-calls N (filter functions with fewer than N calls)
# --format {table,json} (output format)
```

**Analysis Orchestrator:**

```python
def analyze_file(file_path: str) -> tuple[FunctionPriority, ...]:
    """Complete analysis pipeline for a single Python file."""
    # 1. Parse function definitions
    # 2. Count function calls
    # 3. Calculate annotation scores
    # 4. Combine into priority rankings
    # 5. Sort by priority score

def calculate_priority_score(annotation_score: AnnotationScore, call_count: int) -> float:
    """Combine annotation completeness and call frequency into priority score."""
    # Higher priority = more calls + less annotated
    # Example: priority = call_count * (1.0 - annotation_score.total_score)
```

**Rich Output Format:**
- Table showing function name, call count, annotation %, priority score
- Color coding: red for high priority, green for fully annotated
- Summary statistics (total functions analyzed, fully annotated count, etc.)
- Handle edge cases (no functions found, all functions fully annotated)

**Integration Tests:**
- End-to-end test with sample Python file
- Verify CLI argument parsing
- Test output formatting
- Test error handling (invalid files, etc.)

## File Structure After Implementation

```
src/annotation_prioritizer/
├── __init__.py
├── cli.py              # CLI interface (main entry point)
├── models.py           # Data structures
├── parser.py           # AST parsing for function definitions
├── call_counter.py     # AST parsing for call counting
├── scoring.py          # Annotation completeness scoring
├── analyzer.py         # Main analysis orchestrator
└── output.py           # Rich formatting and display

tests/
├── unit/
│   ├── test_parser.py
│   ├── test_call_counter.py
│   ├── test_scoring.py
│   └── test_cli.py
└── integration/
    └── test_end_to_end.py
```

## Key Implementation Notes

**AST Parsing Best Practices:**
- Always handle both `ast.FunctionDef` and `ast.AsyncFunctionDef`
- Use `ast.dump()` for debugging AST structures
- Be careful with node attributes that might be None
- Use `lineno` attribute for source location tracking

**Error Handling:**
- Gracefully handle syntax errors in target files
- Handle file I/O errors
- Provide helpful error messages for CLI users

**Testing Strategy:**
- Use temporary files with known content for tests
- Test with various Python syntax features
- Include edge cases in test data
- Keep integration tests focused on end-to-end behavior

**Performance Considerations:**
- Parse each file only once
- Cache AST if analyzing multiple aspects of same file
- Consider memory usage with large numbers of functions

## Future Extension Points

This initial implementation will create a solid foundation for later additions:
- Import resolution (tracking calls across modules)
- Inheritance handling (method resolution order)
- More sophisticated priority scoring
- Configuration file support
- Multiple output formats

The modular design with separate parser, scorer, and counter components makes these extensions straightforward to add without major refactoring.
