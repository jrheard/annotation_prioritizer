# Annotation Prioritizer

Python type annotation priority analyzer - identifies high-impact functions that need type annotations.

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

```bash
# Run the CLI
annotation-prioritizer

# Run tests
pytest

# Run type checking
pyright

# Run linting
ruff check
ruff format
```

## Development

This project uses:
- Python 3.13+
- uv for dependency management
- ruff for linting and formatting
- pyright for type checking
- pytest for testing

## License

MIT License - see LICENSE file for details.
