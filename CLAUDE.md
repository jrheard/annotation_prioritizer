# Project Overview

This is a Python type annotation priority analyzer that identifies high-impact functions needing type annotations. The project uses modern Python tooling with uv for dependency management.

# Development Environment

This project runs in a VS Code dev container with restricted network access. Only traffic to domains configured in `.devcontainer/init-firewall.sh` is allowed.

# Development Commands

## Common Commands
```bash
# Run the CLI tool
# (The demo_files/ directory contains example Python files for testing the tool,
#  these files are excluded from linting/formatting to demonstrate various scenarios)
annotation-prioritizer filename.py

# Testing
pytest                     # Run all tests
pytest tests/unit/         # Run unit tests only
pytest tests/integration/  # Run integration tests only
pytest --cov=src --cov-report=term-missing --cov-fail-under=100  # Run tests with 100% coverage enforcement

# Type Checking
pyright                    # Run type checker (strict mode enabled)

# Linting and Formatting
ruff check                 # Lint code
ruff check --fix           # Lint and auto-fix issues
ruff format                # Format code

# Pre-commit (runs automatically on commit)
pre-commit run --all-files # Run all hooks manually
```

When you encounter Python linting issues, run `ruff check --fix` and `ruff format` first before trying to fix those issues yourself.
If pre-commit fails with multiple pyright errors or test failures, immediately use the python-lint-fixer subagent instead of fixing manually.
When fixing linting/formatting issues while satisfying pre-commit, ALWAYS `git add` the fixed files before attempting to commit again.

# Architecture

- Entry point: `src/annotation_prioritizer/cli.py:main` - Simple CLI using Rich console
- Package structure: Standard src-layout with `src/annotation_prioritizer/`
- Testing: pytest with unit and integration test separation
- Dependencies: Minimal runtime dependencies (only Rich), comprehensive dev dependencies

# Configuration

- Python version: 3.13+ (specified in pyproject.toml and pyrightconfig.json)
- Type checking: Strict mode enabled for pyright
- Linting: Ruff with ALL rules enabled, no current ignores
- Coverage: 100% coverage requirement
- Pre-commit hooks: ruff (lint + format)

# Programming Style

This project follows functional programming principles:

- Pure functions: Write pure functions wherever possible - functions that don't have side effects and return the same output for the same input
- Frozen dataclasses: Always use `@dataclass(frozen=True)` for structured data. Never use namedtuples or regular classes for data
- Enums: Enums are great. Literal["foo", "bar", "baz"] is OK too in the simplest cases, otherwise prefer enums.
- No inheritance: Avoid inheritance unless absolutely necessary (e.g., when integrating with libraries like Python's AST module). Use bare functions instead
- No pytest fixtures: Prefer normal helper functions over pytest fixtures for test setup
- Test structure: Tests should be bare functions, not methods in test classes. Don't use wrapper classes like `TestSomething` - pytest doesn't need them
- Use `@pytest.mark.parametrize` to test multiple scenarios efficiently instead of writing repetitive test functions
- File organization: Keep non-test Python files focused and split them into smaller modules if they exceed ~400-500 lines of non-documentation code (actual logic, not counting docstrings/comments)

# Documentation Updates

- Keep project_status.md updated: When adding, removing, or changing features, always update `docs/project_status.md` to reflect the current state. This document serves as the authoritative source of truth for what functionality is implemented, planned, or out of scope.
- Update implementation plans: When completing tasks from a plan document in `plans/`, update that plan to mark completed tasks and record any implementation changes or discoveries.
- Always include changes to `dev-diary.txt` in commits (user edits this file during work)

# Commit Messages

Use conventional commits format with precise types:
- `feat:` - New user-facing functionality only (core app features)
- `fix:` - Bug fixes
- `docs:` - Documentation changes (docstrings, comments, README, planning docs, Claude-related markdown files, etc.)
- `refactor:` - Code restructuring without behavior changes
- `test:` - Test changes
- `chore:` - Tooling, dependencies, build config, CI/CD

# Project Structure

- `src/annotation_prioritizer/` - Main package code
- `tests/unit/` - Unit tests
- `tests/integration/` - Integration tests
- `plans/` - Implementation planning documents
  - `plans/pending/` - Implementation plans awaiting work
  - `plans/completed/` - Finished implementations
  - `plans/persistent/` - Reference documents

# Planning and Implementation Guidance

When planning or implementing features, ask clarifying questions about priorities and use cases when:
- The user's stated goals seem to conflict with plan assumptions
- Multiple implementation approaches have significantly different trade-offs

Present options with clear pros/cons rather than assuming the "obvious" choice.
