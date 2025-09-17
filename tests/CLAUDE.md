# Test Guidelines

- Always parse Python code snippets to generate AST nodes for testing rather than manually constructing AST nodes with ast.Call(), ast.Name(), etc.
- Test naming: Unit test filenames should always match the name of the file under test (e.g., `test_foo.py` for `foo.py`)
- No pytest fixtures: Prefer normal helper functions over pytest fixtures for test setup
- Test structure: Tests should be bare functions, not methods in test classes. Don't use wrapper classes like `TestSomething` - pytest doesn't need them
- Use `@pytest.mark.parametrize` to test multiple scenarios efficiently instead of writing repetitive test functions
