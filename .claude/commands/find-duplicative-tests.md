Analyze test files for duplicative tests that essentially test the same functionality despite different implementations or names. Provide numbered recommendations for consolidation. ultrathink.

## Analysis Process

1. **Scan test directories**: Examine all test files in `tests/` directory
2. **Identify test purpose**: Understand what each test is actually validating
3. **Detect duplicates**: Find tests that verify the same behavior despite different approaches
4. **Generate recommendations**: Provide specific suggestions for test consolidation

## Focus Areas

Look for these patterns of test duplication:

- **Same assertions, different setup** - Tests that verify identical outcomes with slightly different input data
- **Overlapping coverage** - Multiple tests that exercise the same code path with minor variations
- **Renamed concepts** - Tests for the same functionality using different terminology
- **Incremental tests** - Series of tests where later ones fully encompass earlier ones
- **Alternative approaches** - Different test methods (e.g., mocking vs integration) testing identical behavior
- **Edge case proliferation** - Multiple tests for essentially the same edge case with trivial differences

## Detection Strategies

- Compare test assertions and expected outcomes
- Analyze code paths exercised by each test
- Look for tests with similar names or docstrings
- Identify tests that fail/pass together consistently
- Check for tests that mock the same dependencies in similar ways
- Review tests that use identical or nearly identical test data

## Output Format

Generate numbered recommendations in this format:

**Recommendation N: [Title]**
- **Priority**: High/Medium/Low
- **Tests identified**: List specific test files and functions
- **Duplication type**: Category of duplication detected
- **Core functionality tested**: What all these tests are actually verifying
- **Consolidation strategy**: How to merge or reorganize the tests
- **Impact**: Test suite reduction and maintenance improvement
- **Suggested consolidated test**: Brief outline of the unified test

## Important Notes

- **READ ONLY**: Do not make any changes to files. Only provide analysis and recommendations.
- **Preserve coverage**: Ensure consolidation doesn't lose important test coverage
- **Be specific**: Include exact file paths and test function names
- **Consider test clarity**: Sometimes slight duplication aids readability - note when this applies
- **Prioritize impact**: Focus on the most egregious duplications first
- **Enable selective implementation**: Number recommendations so user can choose which to implement

## Example Recommendation

**Recommendation 1: Consolidate Error Handling Tests**
- **Priority**: High
- **Tests identified**:
  - `tests/unit/test_parser.py::test_invalid_syntax_error`
  - `tests/unit/test_parser.py::test_malformed_input_raises`
  - `tests/unit/test_parser.py::test_parse_error_handling`
- **Duplication type**: Same assertions, different setup
- **Core functionality tested**: Parser raises SyntaxError for invalid Python code
- **Consolidation strategy**: Merge into single parameterized test with various invalid inputs
- **Impact**: Reduce 3 tests to 1 parameterized test, ~40 lines saved
- **Suggested consolidated test**:
  ```python
  @pytest.mark.parametrize("invalid_code,expected_msg", [
      ("def (:", "invalid syntax"),
      ("class 123:", "invalid syntax"),
      ("import from", "invalid syntax"),
  ])
  def test_parser_handles_invalid_syntax(invalid_code, expected_msg):
      # Single test covering all invalid syntax scenarios
  ```

Begin analysis now.
