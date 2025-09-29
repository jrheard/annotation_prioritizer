# Test Guidelines

- Always parse Python code snippets to generate AST nodes for testing rather than manually constructing AST nodes with ast.Call(), ast.Name(), etc.
- Test naming: Unit test filenames should always match the name of the file under test (e.g., `test_foo.py` for `foo.py`)
- No pytest fixtures: Prefer normal helper functions over pytest fixtures for test setup
- Use `@pytest.mark.parametrize` to test multiple scenarios efficiently instead of writing repetitive test functions

## Unit vs Integration Tests

**Unit tests** (`tests/unit/`):
- Must NOT perform any I/O operations (file system, network, database, etc.)
- Test pure functions and logic in isolation
- Use in-memory data structures and string parsing
- Example: Testing scoring calculations, model creation, AST manipulation from parsed strings

**Integration tests** (`tests/integration/`):
- Tests that perform I/O operations of any kind
- Tests that verify interactions with external systems (file system, etc.)
- Example: Reading/writing files, command-line interface testing with actual files

## Writing Timeless Test Comments

Test comments should describe the current behavior without referencing historical changes or implementation evolution. Future maintainers don't need to know what used to work differently - they need to understand what the code does now.

**Bad examples (avoid these):**
```python
# This is now tracked with variable resolution
# This used to fail but now works
# After the refactor, this is supported
# With the new implementation, this resolves correctly
```

**Good examples (use these instead):**
```python
# calc.add() resolves to Calculator.add through variable tracking
# Instance method calls are tracked when variables have known types
# Variable reassignment uses the final type for all references
# Parameter type annotations enable method resolution
```

The test comments should explain **what** the test verifies and **how** the functionality works, not the history of **when** or **why** it changed.
