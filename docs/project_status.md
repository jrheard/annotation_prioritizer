# Project Status: Type Annotation Priority Analyzer

**Last Updated:** September 16, 2025

## Project Overview

The Type Annotation Priority Analyzer is a Python tool that identifies high-impact functions needing type annotations. It analyzes Python codebases with partial type annotation coverage and prioritizes which functions should be annotated first based on usage frequency and annotation completeness.

**Primary Goal:** Help developers maximize the value of their type annotation efforts by focusing on frequently-called, under-annotated functions.

## Current Implementation Status ✅

### Core Functionality
- **Data Models**: Complete data structures (FunctionInfo, CallCount, AnnotationScore, FunctionPriority)
- **Function Parsing**: AST-based extraction of function definitions, including:
  - Module-level functions and class methods
  - Async functions (`async def`)
  - Parameter type annotations (including *args, **kwargs)
  - Return type annotations
  - Proper qualified names with full scope hierarchy (e.g., `__module__.Calculator.add`)

### Analysis Capabilities
- **Annotation Scoring**: Weighted completeness scoring (75% parameters, 25% return type)
- **Call Counting**: Same-module call tracking for:
  - Direct function calls (`function_name()`)
  - Self method calls (`self.method()`)
  - Static/class method calls (`Calculator.static_method()`)
  - Nested function calls (functions defined inside other functions)
- **Priority Calculation**: Combined metric based on call frequency × annotation incompleteness
- **Conservative Methodology**: Only tracks function calls that can be confidently resolved, avoiding uncertain inferences
- **Scope-Aware Tracking**: Complete scope hierarchy tracking (module/class/function) with typed `Scope` dataclass

### CLI and Output
- **Rich Console Output**: Formatted tables with color coding
- **Single File Analysis**: Processes individual Python files (temporary MVP - directory analysis is the primary goal)
- **Summary Statistics**: Total functions, fully annotated count, high-priority alerts

### Development Infrastructure
- **100% Test Coverage**: Enforced by pre-commit hooks
- **Type Checking**: Strict pyright configuration
- **Linting**: Ruff with comprehensive rule set
- **CI/CD**: GitHub Actions with pre-commit validation

## Known Issues & Bugs 🐛

### Critical Bug: Instance Method Calls Not Counted
```python
class Calculator:
    def add(self, a, b):  # Shows 0 calls instead of 1
        return a + b

def process():
    calc = Calculator()
    return calc.add(5, 7)  # This call is NOT being counted!
```

### Other Limitations
- **Single File Only**: No directory or project-wide analysis (temporary limitation)
- **No Import Support**: Imported classes and functions not tracked
- **No Unresolvable Call Reporting**: Missing calls aren't tracked or reported

### Fixed Issues
- ✅ **False Positives with Constants**: Previously treated constants like `MAX_SIZE` as classes (FIXED via ClassRegistry)

### Import and Multi-File Support Status

**Current State:**
- Tool analyzes one file at a time in isolation
- Cannot resolve imports (`from typing import List`, `import math`, etc.)
- Cannot track calls to imported functions or class methods
- Limited effectiveness on import-heavy codebases

**Future Implementation Path:**
1. **Phase 1: Import Resolution** (Single File)
   - Parse import statements within the analyzed file
   - Build import registry mapping names to modules
   - Resolve imported class/function references
   - Handle common patterns (aliased imports, from imports)
   - Still single-file, but with much better call attribution

2. **Phase 2: Multi-File Analysis** (Directory Support)
   - Analyze entire directories/projects
   - Build cross-file dependency graphs
   - Track calls across module boundaries
   - Aggregate metrics at project level
   - This is the ultimate goal for maximum value

## Completed Improvements ✅

### Class Detection Foundation (Partially Completed 2025-09-16)
**What was implemented:** The foundational ClassRegistry system from commits 1-3 of the class detection plan.

**Completed:**
- ✅ **ClassRegistry data structure**: Immutable registry with `is_class()` method
- ✅ **AST-based class discovery**: ClassDiscoveryVisitor finds all ClassDef nodes
- ✅ **Built-in type recognition**: All Python built-in types via builtins module
- ✅ **False positive elimination**: Constants like `MAX_SIZE` no longer treated as classes
- ✅ **Non-PEP8 class support**: Classes like `xmlParser` correctly identified
- ✅ **Nested class resolution**: `Outer.Inner.method()` calls are properly counted
- ✅ **Integration into CallCountVisitor**: Now uses ClassRegistry (breaking API change)

**NOT Completed:**
- ❌ **Instance method call bug**: `calc = Calculator(); calc.add()` still shows 0 calls
- ❌ **Variable tracking**: No tracking of variable assignments or types
- ❌ **Unresolvable call reporting**: No transparency about what can't be resolved

## In Progress 🚧

### Single-File Accuracy Improvements (Implementation Sequence)
These improvements must be completed in order to achieve very accurate single-file analysis:

1. **Complete Class Detection Improvements** (Step 1 - Foundation) [PARTIALLY COMPLETE]
   - ✅ Commits 1-3 from plan implemented (ClassRegistry foundation)
   - ❌ Commits 4-5 NOT implemented (variable tracking for instance methods)
   - ❌ Instance method call bug NOT fixed (requires variable tracking)

2. **Unresolvable Call Reporting** (Step 2 - Transparency) [NOT STARTED]
   - Track and report calls that cannot be resolved
   - Provides transparency about analysis coverage
   - Prerequisites: Complete class detection improvements first

3. **Scope-Aware Variable Tracking** (Step 3 - Bug Fix) [NOT STARTED]
   - Fix critical instance method call counting bug
   - Track variable assignments and resolve method calls
   - Prerequisites: Complete both class detection and unresolvable call reporting first

### Scope Infrastructure (Completed Foundation)
- ✅ **Scope Stack Foundation**: Replaced `_class_stack` with typed `_scope_stack` using `Scope` dataclass
- ✅ **Function Scope Tracking**: Both parsers now track function scopes in addition to classes
- ✅ **Nested Function Support**: Calls within nested functions can now be resolved
- 🚧 **Variable Tracking**: Next step is to implement scope-aware variable tracking on top of this foundation

## Planned Features 📋

### High Priority
1. **Import Resolution** (Phase 1 - Single File)
   - Parse and track import statements
   - Resolve imported names to their modules
   - Support common import patterns:
     - `import math` → `math.sqrt()`
     - `from typing import List` → `List.append()`
     - `import pandas as pd` → `pd.DataFrame()`
   - Still single-file analysis, but much more effective

2. **Scope-Aware Variable Tracking**
   - Fix instance method call counting bug
   - Track variable assignments (`calc = Calculator()`)
   - Resolve method calls on variables (`calc.add()`)
   - Maintain scope isolation between functions

   **What We Will Track:**
   - Direct instantiation: `calc = Calculator(); calc.add()`
   - Simple parameter annotations: `def foo(calc: Calculator): calc.add()`
   - Annotated variables: `calc: Calculator = get_calculator(); calc.add()`
   - Module-level variables accessible in functions

   **What We Won't Track:**
   - Nested function parent scope variables (currently not implemented, marked for future reconsideration)
   - Unannotated parameters (no type information available)
   - Complex types (Optional, Union, generics - too complex for static analysis)
   - Return values without annotation (can't determine type)
   - Complex expressions (`x if condition else y`, `list[0]`)
   - Dynamic imports and star imports (too complex for reliable static analysis)
   - Decorators (too complex for static analysis)

3. **Unresolvable Call Reporting**
   - Track and report calls that can't be resolved
   - Provide statistics on analysis completeness
   - Help identify missing functionality

### Medium Priority

4. **@property Support**
   - Distinguish properties from regular attributes
   - Count property access as method calls

5. **Enhanced Call Attribution**
   - Support chained calls (`get_calc().add()`)
   - Handle module.function patterns
   - Improve qualified name resolution

## Maybe Someday 🤔

### Advanced Analysis
- **Inheritance Resolution**: Method Resolution Order (MRO) support
- **Class Attribute Tracking**: Instance and class variable types (e.g., `self.calc.add()`)
- **@dataclass Support**: Currently not supported - dataclass fields and methods are not properly tracked
  - Dataclass fields (class variables with type annotations) are not recognized
  - Methods generated by @dataclass decorator (e.g., __init__, __eq__) are not counted
  - Instance attribute access on dataclasses not tracked
  - This is a known limitation to be addressed in future iterations
- **Complex Type Annotations**: Optional, Union, generics support
- **Complexity-Based Weighting**: Cyclomatic complexity in priority scores

### Usability Enhancements
- **JSON Output Format**: Machine-readable results
- **Incremental Analysis**: Cache results for large codebases
- **Performance Optimizations**: Handle very large projects efficiently

## Out of Scope ❌

These features are explicitly **not planned** based on project goals and constraints:

### Automatic Code Modification
- The tool analyzes and recommends only - never modifies source code
- Developers must manually add annotations based on recommendations

### Type Checking Functionality
- Leave type validation to mypy/pyright
- Focus purely on prioritization, not correctness

### Integration with Existing Type Checkers

We explicitly chose not to integrate with existing type checkers for the following reasons:

**Why Not Use Mypy?**
- **API Instability**: Mypy's API breaks with every release (SQLAlchemy deprecated their plugin for this reason)
- **Overhead**: Full type checking for simple variable resolution is overkill
- **Complexity**: We'd use 5% of capabilities while dealing with 100% of complexity
- **Control**: We can't control what mypy trusts or infers

**Why Not Use Pyright?**
- **Not Designed for Programmatic Use**: Pyright is explicitly not designed for programmatic type extraction (confirmed by maintainer)
- **Limited API**: No stable API for extracting type information
- **Performance**: Would require running full type checking for limited use case

**Our Approach**: Build focused, conservative analysis that only tracks what we're confident about, aligned with the project's philosophy of "conservative, accurate analysis"

### Runtime Analysis
- No instrumentation or profiling of running code
- Static analysis only - never executes target code

### Advanced Configuration
- No configuration files (keeps tool simple)
- Command-line flags only for essential options

### Legacy Python Support
- Target modern Python (3.9+) only
- No backwards compatibility concerns

### Dynamic Features
- No dynamic method resolution (`getattr` calls)
- No type inference or automatic annotation generation
- No support for dynamically created classes/methods

### Interface Complexity
- Command-line tool only
- No GUI or web interface planned
