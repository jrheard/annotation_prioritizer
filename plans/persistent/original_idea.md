# Type Annotation Priority Analyzer - Technical Design Document

## Problem Statement

Python codebases with partial type annotation coverage lack tooling to prioritize which functions should be annotated first. Developers need to identify high-impact, under-annotated functions to maximize the value of their type annotation efforts.

Currently available tools (mypy, pytype, MonkeyType) can identify missing annotations but don't provide usage-based prioritization. This leads to inefficient annotation efforts where rarely-used functions get annotated while frequently-called, under-annotated functions remain untouched.

## Goals

### Primary Goals
- **Accurate static analysis**: Provide precise call counts for functions through AST-based analysis
- **Annotation completeness scoring**: Provide detailed metrics on what percentage of parameters/returns are annotated per function
- **Prioritized recommendations**: Rank functions by annotation priority based on usage frequency and annotation completeness
- **Clear, actionable output**: Present results in a readable format that guides developer decision-making

*Note: Fully annotated functions will be excluded from analysis since they don't require further annotation work.*

### Secondary Goals (Future Iterations)
- **Inheritance-aware counting**: Correctly attribute method calls to the appropriate implementation in class hierarchies
- Cross-module analysis with sophisticated import tracking
- Complexity-based weighting (cyclomatic complexity)
- Integration with existing type checkers

## Non-Goals

- **Automatic code modification**: The tool should only analyze and recommend, never modify source code
- **Type checking functionality**: Leave actual type validation to mypy/pyright, focus purely on prioritization
- **Runtime type collection**: No instrumentation, profiling, or execution of target code
- **Backwards compatibility with old Python**: Target modern Python (3.9+) only
- **GUI or web interface**: Command-line tool only, let others build UIs on top
- **Code style or formatting**: Focus on types only, not PEP 8 or other style concerns
- **Third-party annotation format support**: Standard Python typing only, no mypy extensions or stub files
- **Complex decorator analysis**: Beyond basic recognition
- **Support for dynamically created classes/methods**: Focus on statically defined code structures

Additionally, the tool will not handle:
- Dynamic method resolution (e.g., `getattr` calls)
- Type inference or automatic annotation generation

## Technical Approach

### Key Technical Challenges

The tool must solve several complex static analysis problems:

**Import Resolution**
- Track function and class imports across modules (direct imports, aliases, from imports)
- Handle cases where the same name refers to different functions in different contexts
- Resolve qualified names (e.g., `module.function()`) to their actual implementations
- **Star imports**: Calls to functions imported via `from module import *` are treated as unresolvable due to the static analysis complexity of determining which symbols are imported

**Inheritance Resolution**
- Determine which method implementation is actually called in class hierarchies
- Handle method overrides vs inherited methods correctly
- Account for Method Resolution Order (MRO) in complex inheritance scenarios

**Call Attribution**
- Map each call site to the specific function/method implementation it invokes
- Handle both direct function calls and method calls on objects

### Inheritance Resolution Strategy

The most complex aspect involves correctly attributing method calls in inheritance hierarchies:

**For `self.method()` calls:**
1. Determine the containing class of the call site
2. Compute MRO for that class
3. Find the first class in MRO that defines the method
4. Attribute the call to that implementation

**For `obj.method()` calls:**
1. Attempt to determine `obj`'s type from context (assignments, annotations)
2. If type is known, follow same MRO resolution
3. If type is unknown, exclude from call counting and track separately as unresolvable

**Unresolvable Call Handling:**
- Calls where the target cannot be statically determined are excluded from all function call counts
- These calls are tracked separately and reported in analysis output
- This conservative approach ensures priority scores are based only on reliable attribution
- Common categories of unresolvable calls include:
  - Functions imported via star imports (`from module import *`)
  - Dynamic method calls (e.g., `getattr` usage)
  - Calls on objects with unknown types
- Output will include summary statistics (e.g., "Analyzed 1,247 calls, 89 unresolvable (7.1%)")
- Common unresolvable call patterns may be reported to guide future tool improvements

**Method Override Detection:**
- A method is an override if the class defines it AND a parent class also defines it
- Calls in overriding methods count toward the override, not the parent

### Technology Stack

- **Language**: Python 3.11+
- **Package Management**: uv
- **Type Checking**: pyright (strict mode + additional rules TBD)
- **Linting**: ruff (select ALL except disabled rules TBD)
- **Output Formatting**: rich
- **Version Control**: git + GitHub
- **Testing**: pytest with 100% test coverage requirement

## Risk Assessment & Mitigations

### High Risk: Inheritance Analysis Accuracy
**Risk**: Incorrect method resolution leading to wrong call attribution
**Mitigation**:
- Extensive test suite with complex inheritance scenarios
- Cross-validation against known type checker behavior
- Conservative handling of ambiguous cases

### Medium Risk: Import Resolution Complexity
**Risk**: Missing calls due to unresolved imports
**Mitigation**:
- Start with simple import patterns initially
- Clear reporting of unresolved symbols
- Iterative improvement based on real codebase patterns
- Explicit handling of star imports as unresolvable to avoid false positives

### Low Risk: Performance on Large Codebases
**Risk**: Analysis taking too long on large projects
**Mitigation**:
- Profile early and optimize hot paths
- Incremental analysis capabilities
- Configurable analysis scope

## Function vs Method Overloading by Context

### The Problem

Python allows functions and methods with identical names to coexist in the same module, with the context of each call determining which implementation is invoked. For accurate annotation priority analysis, it is critical that the tool treats each of these as completely separate entities, even when they share the same name.

Consider this common scenario:

```python
# data_processing.py
def process_data(data):
    """Module-level function - completely unannotated"""
    return data.strip().upper()

class DataProcessor:
    def process_data(self, data: str) -> str:
        """Instance method - fully annotated"""
        return data.lower()

    def run(self):
        # These are calls to TWO DIFFERENT FUNCTIONS:
        result1 = process_data("hello")        # Calls module function
        result2 = self.process_data("world")   # Calls instance method

def main():
    processor = DataProcessor()

    # More calls to different functions with the same name:
    process_data("test1")           # Module function
    processor.process_data("test2") # Instance method
```

In this example, we have two completely separate callable entities:
1. `process_data` (module-level function) - unannotated, called 2 times
2. `DataProcessor.process_data` (instance method) - fully annotated, called 2 times

### Why This Matters

If the analyzer incorrectly conflates these two functions, it could:

**Scenario 1: False Deprioritization**
- Treat all 4 calls as going to the fully-annotated instance method
- Conclude the module-level function doesn't need attention (0 apparent calls)
- Miss a high-priority annotation target

**Scenario 2: False Prioritization**
- Treat all 4 calls as going to the unannotated module function
- Conclude the module function is extremely high-priority
- Waste effort on a function that actually gets fewer calls than reported

**Scenario 3: Incorrect Aggregation**
- Merge statistics across both functions
- Report confusing annotation completeness scores (partially annotated when one is fully annotated and one is not)

### Additional Complexity Examples

The problem extends beyond simple function/method pairs:

```python
# Multiple overloading contexts
from utils import process_data as imported_process  # External function

def process_data(x):           # Local function
    return x * 2

class Handler:
    @staticmethod
    def process_data(x):       # Static method
        return x + 1

    @classmethod
    def process_data(cls, x):  # Class method (same name!)
        return x - 1

    def process_data(self, x): # Instance method (same name!)
        return x / 2

# Each call must resolve to the correct target:
process_data(5)              # Local function
Handler.process_data(5)      # Static method OR class method (context-dependent)
Handler().process_data(5)    # Instance method
imported_process(5)          # External function
```

### Success Criteria

We will know this problem is successfully solved when:

1. **Distinct Call Attribution**: Each function/method with the same name maintains separate call counts and annotation scores
2. **Context-Aware Resolution**: `process_data()` calls correctly resolve based on their scope and calling context
3. **Accurate Prioritization**: Priority rankings reflect the actual usage patterns of each distinct callable entity
4. **Transparent Reporting**: Output clearly distinguishes between `process_data` (function) and `DataProcessor.process_data` (method) in all reports

The analyzer must implement robust scope tracking and name resolution that mirrors Python's own LEGB (Local, Enclosing, Global, Built-in) lookup rules to achieve this level of precision.