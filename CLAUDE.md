# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a Python type annotation priority analyzer that identifies high-impact functions needing type annotations. The project uses modern Python tooling with uv for dependency management.

## Development Commands

### Common Commands
```bash
# Run the CLI tool
annotation-prioritizer

# Testing
pytest                     # Run all tests
pytest tests/unit/         # Run unit tests only
pytest tests/integration/  # Run integration tests only
pytest --cov=src          # Run tests with coverage

# Type Checking
pyright                    # Run type checker (strict mode enabled)

# Linting and Formatting
uv run --with ruff ruff check                 # Lint code
uv run --with ruff ruff check --fix           # Lint and auto-fix issues
uv run --with ruff ruff format                # Format code

# Pre-commit (runs automatically on commit)
pre-commit run --all-files # Run all hooks manually
```

## Architecture

- **Entry point**: `src/annotation_prioritizer/cli.py:main` - Simple CLI using Rich console
- **Package structure**: Standard src-layout with `src/annotation_prioritizer/`
- **Testing**: pytest with unit and integration test separation
- **Dependencies**: Minimal runtime dependencies (only Rich), comprehensive dev dependencies

## Configuration

- **Python version**: 3.13+ (specified in pyproject.toml and pyrightconfig.json)
- **Type checking**: Strict mode enabled for pyright
- **Linting**: Ruff with ALL rules enabled, no current ignores
- **Coverage**: 100% coverage requirement
- **Pre-commit hooks**: ruff (lint + format)

## Programming Style

This project follows functional programming principles:

- **Pure functions**: Write pure functions wherever possible - functions that don't have side effects and return the same output for the same input
- **Frozen dataclasses**: Always use `@dataclass(frozen=True)` for structured data. Never use namedtuples or regular classes for data
- **No inheritance**: Avoid inheritance unless absolutely necessary (e.g., when integrating with libraries like Python's AST module). Use bare functions instead
- **No pytest fixtures**: Prefer normal helper functions over pytest fixtures for test setup
- **Commit messages**: Use conventional commits format: `type: description` (e.g., `feat: add parser`, `fix: handle edge case`, `docs: update readme`)

## Project Structure

- `src/annotation_prioritizer/` - Main package code
- `tests/unit/` - Unit tests
- `tests/integration/` - Integration tests
- `tests/conftest.py` - Shared pytest fixtures