# Project Status: Type Annotation Priority Analyzer

**Last Updated:** 2025-09-30

## Project Overview

The Type Annotation Priority Analyzer is a Python tool that identifies high-impact functions needing type annotations. It analyzes Python codebases with partial type annotation coverage and prioritizes which functions should be annotated first based on usage frequency and annotation completeness.

**Primary Goal:** Help developers maximize the value of their type annotation efforts by focusing on frequently-called, under-annotated functions.

**Analysis Type:** This is a static analyzer that counts lexical function calls in the source code, not runtime execution counts.

## Current Implementation Status ✅

### Core Functionality
- **Data Models**: Complete data structures (FunctionInfo, CallCount, AnnotationScore, FunctionPriority)
- **Function Parsing**: AST-based extraction of function definitions, including:
  - Module-level functions and class methods
  - Async functions (`async def`)
  - Parameter type annotations (including *args, **kwargs)
  - Return type annotations
  - Proper qualified names with full scope hierarchy (e.g., `__module__.Calculator.add`)
- **Type Safety**: QualifiedName type wrapper with make_qualified_name() factory for type-safe qualified name handling
- **Position-Aware Name Resolution**: NameBindingCollector and PositionIndex provide efficient, position-aware resolution:
  - Single-pass collection of all name bindings (imports, functions, classes, variables)
  - O(log k) binary search lookup where k is the number of bindings for a name in a scope
  - Correctly handles Python's shadowing semantics (later definitions shadow earlier ones)
  - Two-phase resolution for variable target classes

### Analysis Capabilities
- **Annotation Scoring**: Weighted completeness scoring (75% parameters, 25% return type)
- **Call Counting**: Same-module call tracking for:
  - Direct function calls (`function_name()`)
  - Self method calls (`self.method()`)
  - Static/class method calls (`Calculator.static_method()`)
  - Nested function calls (functions defined inside other functions)
  - Class instantiations (`Calculator()` counts as call to `Calculator.__init__`)
- **Variable Tracking**: Position-aware variable resolution through PositionIndex:
  - Direct instantiation: `calc = Calculator(); calc.add()`
  - Variable reassignment tracking with position-aware shadowing
  - Scope-aware resolution (checks current scope, then parent scopes)
  - Two-phase resolution: collect bindings first, then resolve variable targets
  - Note: Parameter annotations (`def foo(calc: Calculator)`) not yet tracked for variable resolution
- **Priority Calculation**: Combined metric based on call frequency × annotation incompleteness
- **Conservative Methodology**: Only tracks function calls that can be confidently resolved, avoiding uncertain inferences
- **Scope-Aware Tracking**: Complete scope hierarchy tracking (module/class/function) with typed `Scope` dataclass
- **Import Tracking (Phase 1 Complete)**: Tracks all import statements with source module information:
  - Module imports: `import math`, `import pandas as pd`
  - From imports: `from typing import List`
  - Relative imports: `from . import utils`
  - Scope-aware visibility (imports in functions only visible in that function)
  - Foundation for future multi-file analysis (Phase 2)
  - Note: Imported names are tracked but not resolved in single-file analysis
- **Unresolvable Call Reporting**: Full transparency for calls that cannot be resolved statically:
  - UnresolvableCall model with line number and call text
  - Accurate multi-line call text extraction using ast.get_source_segment()
  - Summary and examples in CLI output

### Class Instantiation Tracking
- **Synthetic __init__ Generation**: Classes without explicit constructors have synthetic `__init__` methods generated
- **Instantiation Counting**: All `ClassName()` calls are tracked as calls to `ClassName.__init__`
- **Nested Class Support**: Instantiations like `Outer.Inner()` and `Outer.Middle.Inner()` are properly tracked
- **Count All Attempts**: Instantiations with incorrect parameters are still counted (we're a prioritizer, not a type checker)
- **Limitations**:
  - Synthetic `__init__` methods always have just `(self)` as parameter - no inference from parent classes
  - Class reference assignments (`CalcClass = Calculator; CalcClass()`) are not supported
  - Inheritance-aware parameter inference is future work

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
- **Single File Only**: No directory or project-wide analysis (Phase 2 future work)
- **Import Resolution Not Implemented**: Imports are tracked but not resolved
  - Tool knows `sqrt` was imported from `math`
  - Cannot resolve what `math.sqrt` refers to without analyzing math module
  - Calls to imported functions are tracked as unresolvable

#### Call Tracking Limitations
The following patterns are not yet supported for call counting:
- **Nested class instantiation variable tracking**: `inner = Outer.Inner(); inner.method()` - variable type not tracked
- **Method chaining from returns**: `get_calculator().add()` - requires return type inference
- **Indexing operations**: `calculators[0].add()` - requires collection content tracking
- **Attribute access chains**: `self.calc.add()` - requires object attribute type tracking
- **Collection type annotations**: `calculators: list[Calculator]` - generics not handled
- **Cross-module types**: `from module import Calculator` - imports tracked but not resolved (Phase 2 work)
- **Duplicate function definitions**: Functions redefined with the same name in the same file will share call counts (intentionally unsupported - uncommon pattern)

### Fixed Issues
- ✅ **Instance Method Calls Not Counted**: Previously `calc = Calculator(); calc.add()` showed 0 calls (FIXED via variable tracking)
- ✅ **False Positives with Constants**: Previously treated constants like `MAX_SIZE` as classes (FIXED via position-aware resolution)
- ✅ **Import Shadowing Bugs**: Previously failed to handle cases where imports were shadowed by local definitions (FIXED via PositionIndex with position-aware binary search resolution, issue #31)

### Import and Multi-File Support Status

**Current State (Phase 1 Complete):**
- Tool analyzes one file at a time in isolation
- **Import tracking**: All imports are tracked with source module information
  - Knows that `sqrt` was imported from `math`
  - Distinguishes imported names from unknown names
  - Tracks scope visibility of imports
- **Import resolution**: Not yet implemented (Phase 2 work)
  - Cannot resolve what `math.sqrt` refers to without analyzing math module
  - Calls to imported functions are tracked as unresolvable
- Limited effectiveness on import-heavy codebases (will improve with Phase 2)

**Future Implementation Path:**
1. **Phase 2: Multi-File Analysis** (Directory Support) - NEXT GOAL
   - Analyze entire directories/projects
   - Build cross-file dependency graphs
   - Resolve imports by analyzing imported modules
   - Track calls across module boundaries
   - Aggregate metrics at project level
   - This is the ultimate goal for maximum value

## In Progress 🚧

None currently.

## Planned Features 📋

### High Priority
1. **Multi-File Analysis** (Phase 2 - Directory Support)
   - Analyze entire directories/projects
   - Build cross-file dependency graphs
   - Resolve imports by analyzing imported modules
   - Track calls across module boundaries
   - Aggregate metrics at project level
   - Builds on Phase 1 import tracking (already complete)

2. **Inheritance Resolution**
   - Track class inheritance hierarchies
   - Resolve method calls on subclasses to parent class methods
   - Support Method Resolution Order (MRO)
   - Example: `dog.move()` where `Dog` inherits from `Animal` → counts `Animal.move`

### Medium Priority

3. **Parameter Type Annotation Tracking**
   - Track parameter type annotations for variable resolution
   - Support patterns like `def foo(calc: Calculator): calc.add()`
   - Currently only tracks direct instantiation (`calc = Calculator()`)
   - Would enable more comprehensive variable resolution

4. **Return Type Inference**
   - Track function return types to enable method chaining
   - Support patterns like `get_calc().add()`
   - Would require significant type inference infrastructure

5. **@property Support**
   - Distinguish properties from regular attributes
   - Count property access as method calls
   - Properties are already discovered, just need to track access
   - Example: `person.full_name` → counts as call to `Person.full_name` property
   - **Note**: Most valuable AFTER return type inference is implemented
   - Without return types, can't track chained calls from properties (e.g., `person.name.upper()`)

## Maybe Someday 🤔

### Performance

- **Parallelism** - Scan multiple files in parallel

### Advanced Analysis
- **Class Attribute Tracking**: Instance and class variable types (already noted in limitations as `self.calc.add()`)
- **@dataclass Field Attribute Tracking**: While dataclass instantiation and direct method calls work, accessing methods through dataclass field attributes is not tracked
  - Example: `config.calculator.add()` where `calculator` is a dataclass field
  - This is part of the broader attribute chain tracking limitation
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
