# Annotation Prioritizer

Python type annotation priority analyzer - identifies high-impact functions that need type annotations.

NOTE: This codebase is ~10% intended to be actually useful, but is ~90% just a sandbox for me to experiment with Claude Code.

## Overview

This tool analyzes Python codebases with partial type annotation coverage and prioritizes which functions should be annotated first based on usage frequency and annotation completeness.

## Installation

```bash
# Install dependencies
uv sync

# Install pre-commit hooks
pre-commit install
```

## Usage

The `demo_files/` directory contains example Python files you can use to test the tool.

```bash
# Run the CLI on a Python file
annotation-prioritizer path/to/file.py

# Try it with the demo files
annotation-prioritizer demo_files/mixed_annotations.py
annotation-prioritizer demo_files/complex_cases.py

# Run tests (with 100% coverage requirement)
pytest
pytest --cov=src --cov-report=term-missing --cov-fail-under=100

# Run type checking (strict mode)
pyright

# Run linting and formatting
ruff check
ruff check --fix  # Auto-fix issues
ruff format
```

## License

MIT License - see LICENSE file for details.
