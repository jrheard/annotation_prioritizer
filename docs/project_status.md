# Project Status: Type Annotation Priority Analyzer

**Last Updated:** September 14, 2025

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
# This pattern is currently broken:
class Calculator:
    def add(self, a, b):  # Shows 0 calls instead of 1
        return a + b

def process():
    calc = Calculator()
    return calc.add(5, 7)  # This call is NOT being counted!
```

### Other Limitations
- **Complex Qualified Calls**: `obj.attr1.attr2.method()` pattern incomplete
- **Single File Only**: No directory or project-wide analysis (temporary limitation - directory analysis is the primary roadmap goal)
- **No Import Tracking**: Cross-module calls not resolved
- **No Unresolvable Call Reporting**: Missing calls aren't tracked or reported

## In Progress 🚧

### Scope Infrastructure (Partially Complete)
- ✅ **Scope Stack Foundation**: Replaced `_class_stack` with typed `_scope_stack` using `Scope` dataclass
- ✅ **Function Scope Tracking**: Both parsers now track function scopes in addition to classes
- ✅ **Nested Function Support**: Calls within nested functions can now be resolved
- 🚧 **Variable Tracking**: Next step is to implement scope-aware variable tracking on top of this foundation

## Planned Features 📋

### High Priority
1. **Scope-Aware Variable Tracking**
   - Fix instance method call counting bug
   - Track variable assignments (`calc = Calculator()`)
   - Resolve method calls on variables (`calc.add()`)
   - Maintain scope isolation between functions

2. **Directory Analysis** (Primary Goal)
   - Process entire Python projects
   - Analyze multiple files in a single run
   - Aggregate statistics across modules
   - Will replace single-file analysis as the primary interface

3. **Unresolvable Call Reporting**
   - Track and report calls that can't be resolved
   - Provide statistics on analysis completeness
   - Help identify missing functionality

### Medium Priority
4. **Import Resolution**
   - Track function imports across modules
   - Handle `from module import function`
   - Support import aliases
   - Enable cross-module call counting

5. **Enhanced Call Attribution**
   - Support chained calls (`get_calc().add()`)
   - Handle module.function patterns
   - Improve qualified name resolution

## Maybe Someday 🤔

### Advanced Analysis
- **Inheritance Resolution**: Method Resolution Order (MRO) support
- **Class Attribute Tracking**: Instance and class variable types
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
- Mypy API is unstable and breaks frequently
- Pyright not designed for programmatic type extraction
- Adds complexity without sufficient benefit

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
