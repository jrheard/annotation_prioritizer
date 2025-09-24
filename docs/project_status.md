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

### Current Limitations

#### Analysis Scope
- **Single File Only**: No directory or project-wide analysis (temporary limitation)
- **No Import Support**: Imported classes and functions not tracked

#### Call Tracking Limitations
The following patterns are not yet supported for call counting:
- **Method chaining from returns**: `get_calculator().add()` - requires return type inference
- **Indexing operations**: `calculators[0].add()` - requires collection content tracking
- **Attribute access chains**: `self.calc.add()` - requires object attribute type tracking
- **Collection type annotations**: `calculators: list[Calculator]` - generics not handled
- **Cross-module types**: `from module import Calculator` - import resolution not implemented

### Fixed Issues
- ✅ **Instance Method Calls Not Counted**: Previously `calc = Calculator(); calc.add()` showed 0 calls (FIXED via variable tracking)
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

### Scope-Aware Variable Tracking (Completed 2025-09-22)
**What was implemented:** Two-pass analysis system for tracking variable-to-type mappings and resolving instance method calls.

**Completed:**
- ✅ **Variable Registry**: Data models and utilities for tracking variable types
- ✅ **Variable Discovery Visitor**: AST visitor that builds registry of variable-to-type mappings
- ✅ **Two-Pass Analysis**: First pass discovers variables, second pass counts calls
- ✅ **Instance Method Resolution**: `calc = Calculator(); calc.add()` now correctly counted
- ✅ **Parameter Type Annotations**: `def foo(calc: Calculator)` enables method resolution
- ✅ **Variable Type Annotations**: `calc: Calculator = get_calculator()` tracked
- ✅ **Scope Isolation**: Variables in different scopes tracked separately
- ✅ **Parent Scope Access**: Nested functions can access parent scope variables
- ✅ **Module-Level Variables**: Top-level variables accessible in all functions

**Patterns Now Supported:**
- Direct instantiation: `calc = Calculator(); calc.add()`
- Parameter annotations: `def foo(calc: Calculator): calc.add()`
- Variable annotations: `calc: Calculator = ...`
- Class references: `CalcClass = Calculator` (tracked but not for instantiation)
- Variable reassignment: Tracks the most recent type assignment

**Patterns Still Deferred (Future Work):**
- Nested class instantiation variable tracking: `inner = Outer.Inner(); inner.method()` (variable type not tracked)
- Method chaining from returns: `get_calculator().add()` (no return type tracking)
- Indexing operations: `calculators[0].add()` (no collection content tracking)
- Attribute access chains: `self.calc.add()` (no object attribute tracking)
- Collection type annotations: `calculators: list[Calculator]` (generics not handled)
- Import tracking: `from module import Calculator` (cross-module not supported)

### Scope Infrastructure (Completed Foundation)
- ✅ **Scope Stack Foundation**: Replaced `_class_stack` with typed `_scope_stack` using `Scope` dataclass
- ✅ **Function Scope Tracking**: Both parsers now track function scopes in addition to classes
- ✅ **Nested Function Support**: Calls within nested functions can now be resolved

### Unresolvable Call Reporting (Completed 2025-09-19)
**What was implemented:** Full transparency system for tracking calls that cannot be resolved statically.

**Completed:**
- ✅ **UnresolvableCall model**: Data structure with line number and call text
- ✅ **Call tracking in CallCountVisitor**: Tracks all unresolvable calls during traversal
- ✅ **AnalysisResult integration**: Returns both priorities and unresolvable calls
- ✅ **CLI output support**: Displays summary and examples of unresolvable calls
- ✅ **Accurate call text extraction**: Uses ast.get_source_segment() for multi-line calls
- ✅ **Full test coverage**: Comprehensive tests for all unresolvable call scenarios

### QualifiedName Type Safety (Completed 2025-09-17)
**What was implemented:** Type-safe qualified name handling using NewType.

**Completed:**
- ✅ **QualifiedName NewType**: Type-safe wrapper for qualified name strings
- ✅ **make_qualified_name() factory**: Single entry point for creating QualifiedName instances
- ✅ **Full codebase migration**: All qualified name usage converted to use QualifiedName type
- ✅ **Type checking enforcement**: Pyright validates proper usage throughout codebase

### Class Detection Foundation (Completed 2025-09-16)
**What was implemented:** Full AST-based class detection system eliminating all false positives.

**Completed:**
- ✅ **ClassRegistry data structure**: Immutable registry with `is_known_class()` method
- ✅ **AST-based class discovery**: ClassDiscoveryVisitor finds all ClassDef nodes
- ✅ **False positive elimination**: Constants like `MAX_SIZE` no longer treated as classes
- ✅ **Non-PEP8 class support**: Classes like `xmlParser` correctly identified
- ✅ **Nested class resolution**: `Outer.Inner.method()` calls are properly counted
- ✅ **Integration into CallCountVisitor**: Now uses ClassRegistry for definitive class identification
- ✅ **Full test coverage**: Comprehensive tests for all class detection scenarios

**Note:** Class detection now works correctly for all class patterns including nested classes.

## In Progress 🚧

None currently.

## Planned Features 📋

### High Priority
1. **Class Instantiation Tracking** (Partially Complete)
   - ✅ Track direct `ClassName()` calls as calls to `__init__` methods
   - ✅ Generate synthetic `__init__` for classes without explicit constructors
   - ✅ Count instantiations properly for priority scoring
   - ✅ Support nested class instantiation (`Outer.Inner()`, `Outer.Middle.Inner()`)
     - Note: This counts the call to `Outer.Inner.__init__`, but doesn't track the variable type for subsequent method calls
   - ⏸️ **Deferred:** Class reference assignments (`CalcClass = Calculator; CalcClass()`)

2. **@property Support**
   - Distinguish properties from regular attributes
   - Count property access as method calls
   - Properties are already discovered, just need to track access
   - Example: `person.full_name` → counts as call to `Person.full_name` property

3. **Import Resolution** (Phase 1 - Single File)
   - Parse and track import statements
   - Resolve imported names to their modules
   - Support common import patterns:
     - `import math` → `math.sqrt()`
     - `from typing import List` → `List.append()`
     - `import pandas as pd` → `pd.DataFrame()`
   - Still single-file analysis, but much more effective

4. **Inheritance Resolution**
   - Track class inheritance hierarchies
   - Resolve method calls on subclasses to parent class methods
   - Support Method Resolution Order (MRO)
   - Example: `dog.move()` where `Dog` inherits from `Animal` → counts `Animal.move`

### Medium Priority

5. **Return Type Inference**
   - Track function return types to enable method chaining
   - Support patterns like `get_calc().add()`
   - Would require significant type inference infrastructure

## Maybe Someday 🤔

### Performance

- **Parallelism** - Scan multiple files in parallel

### Advanced Analysis
- **Class Attribute Tracking**: Instance and class variable types (already noted in limitations as `self.calc.add()`)
- **@dataclass Support**: Currently not supported - dataclass fields and methods are not properly tracked
  - Dataclass fields (class variables with type annotations) are not recognized
  - Methods generated by @dataclass decorator (e.g., __init__, __eq__) are not counted
  - Instance attribute access on dataclasses not tracked
  - This is a known limitation to be addressed in future iterations
- **Complex Type Annotations**: Optional, Union, generics (already noted in limitations for collections like `list[Calculator]`)
- **Collection Content Tracking**: Track types within lists, dicts, etc. to support `calculators[0].add()`
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
