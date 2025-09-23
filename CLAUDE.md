# Project Overview

This is a Python type annotation priority analyzer that identifies high-impact functions needing type annotations. Uses uv for dependency management.

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
pytest
pytest tests/unit/         # Run unit tests only
pytest tests/integration/  # Run integration tests only
pytest --cov=src --cov-report=term-missing --cov-fail-under=100

# Type Checking
pyright

# Linting and Formatting
ruff check --fix           # Lint and auto-fix issues
ruff format                # Format code

# Pre-commit (runs automatically on commit)
pre-commit run --all-files # Run all hooks manually
```

When you encounter Python linting issues, run `ruff check --fix` and `ruff format` first before trying to fix those issues yourself.
If you encounter many pyright errors or test failures, immediately use the python-lint-fixer subagent instead of fixing manually.
When fixing linting/formatting issues while satisfying pre-commit, ALWAYS `git add` the fixed files before attempting to commit again.

# Architecture

- Entry point: `src/annotation_prioritizer/cli.py:main` - Simple CLI using Rich console
- Package structure: Standard src-layout with `src/annotation_prioritizer/`
- Testing: pytest with unit and integration test separation

# Configuration

- Python version: 3.13+
- Type checking: Pyright on strict mode + extra rules
- Linting: Ruff with ALL rules enabled, some ignores
- Coverage: 100% coverage requirement
- Pre-commit hooks: ruff (lint + format)

# Programming Style

This project follows functional programming principles:

- Write pure functions wherever possible.
- Always use `@dataclass(frozen=True)` for structured data. Never use namedtuples or regular classes for data
- Prefer enums when representing closed sets of known values. Literal["foo", "bar", "baz"] is OK too in the simplest cases.
- Immutability: Where possible, functions/methods/classes should take tuples, frozensets, etc. as input rather than lists, sets, etc.
- Avoid inheritance unless absolutely necessary (e.g., when integrating with libraries like Python's AST module). Use bare functions instead
- Look for existing implementations before writing new code. Extract and reuse nontrivial logic (>10 lines or complex business rules) rather than duplicating it
- Always use absolute imports.

# Documentation Updates

- Keep project_status.md updated: When adding, removing, or changing features, always update `docs/project_status.md` to reflect the current state. This document serves as the authoritative source of truth for what functionality is implemented, planned, or out of scope.
- When completing tasks from a plan document in `plans/`, update that plan to mark completed tasks and record any implementation changes or discoveries.
- Always add `dev-diary.txt` when making commits (user edits this file during work)

# Commit Messages

Use conventional commits format with precise types:
- `feat:` - New user-facing functionality only
- `fix:` - Bug fixes
- `docs:` - Documentation changes (docstrings, comments, markdown files, etc)
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

# Sub-agents

- Proactively use sub-agents for complex tasks to conserve context in our main conversation thread. Use our custom general-purpose opus-agent agent, NOT the built-in general-purpose agent, when spawning sub-agents.
- If you encounter lots of failing tests, spawn a sub-agent to fix them.
