Analyze $ARGUMENTS for code duplication, verbosity, and opportunities for helper functions. Provide numbered recommendations for improvements without making any changes. ultrathink.

## Analysis Process

1. **Read existing test helpers**: Examine `tests/helpers/` directory to understand available utility functions
2. **Scan specified test files**
3. **Identify patterns**: Look for repetitive code, verbose setup/teardown, and common utilities that could be extracted
4. **Generate recommendations**: Provide specific, actionable suggestions with examples

## Focus Areas

Look for these general patterns across all test files:

- **Repeated setup/teardown code** - File creation, object initialization, cleanup
- **Verbose object construction** - Complex data structures built the same way multiple times
- **Boilerplate patterns** - Similar test utilities, assertions, or mock setups
- **Duplicated test data** - Hardcoded values, strings, or configurations used across files
- **Common assertions** - Complex verification logic repeated in multiple tests
- **Resource management** - File handles, connections, or other resources needing cleanup

## Output Format

Generate numbered recommendations in this format:

**Recommendation N: [Title]**
- **Priority**: High/Medium/Low
- **Files affected**: List specific files and line ranges
- **Current duplication**: Show 2-3 examples of the repeated pattern
- **Suggested solution**: Either reuse existing helper or create new one (prefer reusing when possible)
- **Impact**: Estimate lines of code saved and maintainability improvement
- **Example usage**: Show how tests would look after refactoring

## Important Notes

- **READ ONLY**: Do not make any changes to files. Only provide analysis and recommendations.
- **Prefer existing helpers**: Always check if an existing helper can be reused before suggesting a new one. Only recommend creating new helpers when no suitable existing helper exists.
- **Be specific**: Include exact file paths and line numbers where patterns occur
- **Prioritize impact**: Focus on the most frequently duplicated patterns first
- **Suggest concrete solutions**: For reuse, show the existing helper; for new helpers, provide function signatures
- **Enable selective implementation**: Number recommendations so user can choose which ones to implement

## Example Recommendation Formats

**Recommendation 1: Reuse Existing Helper**
- **Priority**: High
- **Files affected**: `tests/unit/test_parser.py:45-52`, `tests/unit/test_output.py:12-18`
- **Current duplication**: 8 instances of manual StringIO + Console setup
- **Suggested solution**: Use existing `capture_console_output()` from `tests/helpers/console.py`
- **Impact**: ~30 lines of code eliminated, consistent output testing
- **Example usage**: `with capture_console_output() as output: display_results(console, data)`

**Recommendation 2: Create New Helper**
- **Priority**: Medium
- **Files affected**: `tests/unit/test_parser.py:12-19,47-54,75-82`
- **Current duplication**: 15+ instances of identical tempfile creation and cleanup
- **Suggested solution**: Create new helper (no suitable existing helper found)
  ```python
  # tests/helpers/temp_files.py
  @contextmanager
  def temp_python_file(content: str) -> Iterator[str]:
      """Create temporary Python file with content, auto-cleanup."""
  ```
- **Impact**: ~60 lines of code eliminated, consistent error handling
- **Example usage**: `with temp_python_file(code) as path: result = parse_function_definitions(path)`

Begin analysis now.
