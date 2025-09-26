# Project Status: Type Annotation Priority Analyzer

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
- **Class Detection**: AST-based ClassRegistry that definitively identifies all classes, eliminating false positives

### Analysis Capabilities
- **Annotation Scoring**: Weighted completeness scoring (75% parameters, 25% return type)
- **Call Counting**: Same-module call tracking for:
  - Direct function calls (`function_name()`)
  - Self method calls (`self.method()`)
  - Static/class method calls (`Calculator.static_method()`)
  - Nested function calls (functions defined inside other functions)
  - Class instantiations (`Calculator()` counts as call to `Calculator.__init__`)
- **Variable Tracking**: VariableRegistry for tracking variable-to-type mappings:
  - Builds registry upfront from AST analysis
  - Direct instantiation: `calc = Calculator(); calc.add()`
  - Parameter annotations: `def foo(calc: Calculator): calc.add()`
  - Variable annotations: `calc: Calculator = ...`
  - Variable reassignment tracking (most recent type)
  - Scope isolation with parent scope access
- **Priority Calculation**: Combined metric based on call frequency × annotation incompleteness
- **Conservative Methodology**: Only tracks function calls that can be confidently resolved, avoiding uncertain inferences
- **Scope-Aware Tracking**: Complete scope hierarchy tracking (module/class/function) with typed `Scope` dataclass
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
- **Single File Only**: No directory or project-wide analysis (temporary limitation)
- **No Import Support**: Imported classes and functions not tracked

#### Call Tracking Limitations
The following patterns are not yet supported for call counting:
- **Nested class instantiation variable tracking**: `inner = Outer.Inner(); inner.method()` - variable type not tracked
- **Method chaining from returns**: `get_calculator().add()` - requires return type inference
- **Indexing operations**: `calculators[0].add()` - requires collection content tracking
- **Attribute access chains**: `self.calc.add()` - requires object attribute type tracking
- **Collection type annotations**: `calculators: list[Calculator]` - generics not handled
- **Cross-module types**: `from module import Calculator` - import resolution not implemented
- **Duplicate function definitions**: Functions redefined with the same name in the same file will share call counts (intentionally unsupported - uncommon pattern)

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

## In Progress 🚧

None currently.

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

2. **Inheritance Resolution**
   - Track class inheritance hierarchies
   - Resolve method calls on subclasses to parent class methods
   - Support Method Resolution Order (MRO)
   - Example: `dog.move()` where `Dog` inherits from `Animal` → counts `Animal.move`

### Medium Priority

3. **Return Type Inference**
   - Track function return types to enable method chaining
   - Support patterns like `get_calc().add()`
   - Would require significant type inference infrastructure

4. **@property Support**
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
