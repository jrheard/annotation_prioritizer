# Test Codebases for Type Annotation Priority Analyzer

## Selection Criteria

For initial testing of the Type Annotation Priority Analyzer, we want codebases that have:
- Partial type annotation coverage (mix of annotated and unannotated functions)
- Reasonable complexity with class hierarchies and inheritance
- Multiple modules with imports between them
- Manageable size (not overwhelming for initial testing)

## Recommended Test Codebases

### Web Frameworks & Tools
- **FastAPI** (~50k LOC) - Modern framework with good but incomplete type annotations, lots of inheritance and decorators
- **Starlette** (~15k LOC) - FastAPI's foundation, cleaner and smaller codebase with similar patterns
- **Typer** (~10k LOC) - CLI framework by the FastAPI author, mix of typed and untyped code
- **Pydantic v1** - Widely used validation library with interesting inheritance patterns (v2 might be too heavily typed)

### Data Processing & Scientific
- **Pandas** (specific modules) - Instead of the full codebase, focus on core modules like `pandas/core/frame.py` or `pandas/io/`
- **Requests** (~15k LOC) - Popular HTTP library, mix of annotation levels, good method overriding examples
- **Click** (~20k LOC) - CLI framework with decorators and inheritance, partially typed
- **Pillow** (PIL) - Image processing with class hierarchies, mix of typed/untyped code

### Developer Tools
- **Black** (~15k LOC) - Code formatter with some type annotations but not complete coverage
- **Pytest** (core modules) - Well-structured with plugins and inheritance, partial typing. Investigation shows ~50% of files (34/68) have `mypy: allow-untyped-defs` directive, with fully typed modules like `outcomes.py`, `deprecated.py` vs partially typed `fixtures.py`, `config/__init__.py`. Properties and abstract methods frequently lack return type annotations (e.g., `def node(self):`, `def function(self):` in fixtures.py). Pre-commit runs both mypy (strict mode) and pyright (basic mode), with a comment noting pyright passing is "work in progress". Test files also mixed - some like `test_fixture.py` have `disallow-untyped-defs` while most allow untyped.
- **Flake8** - Linting tool with plugin architecture, good for testing import resolution
- **Twine** (~5k LOC) - PyPI upload tool, smaller but non-trivial

### Utilities & Libraries
- **Rich** (~30k LOC) - Terminal formatting library, modern codebase with mixed annotation coverage
- **Httpx** (~25k LOC) - Modern HTTP client, similar complexity to requests but more recent
- **Pathlib2** or similar filesystem utilities - Good for testing with lots of method overriding

## Top Initial Candidates

### Primary Recommendations (Start Here)
1. **Typer** - Modern codebase with manageable size, clear structure, mixed annotation coverage
2. **Rich** - Well-structured terminal library with diverse usage patterns
3. **Starlette** - FastAPI foundation but more focused and smaller

### Secondary Candidates (Next Phase)
1. **Requests** - Battle-tested library with good complexity
2. **Click** - Mature CLI framework with decorator patterns
3. **Black** - Code formatter with interesting AST usage

## Why These Are Good Choices

- **Modern codebases** likely to have some type annotations already
- **Manageable size** for thorough analysis during development
- **Well-structured** with clear inheritance patterns
- **Created by quality-focused developers**
- **Diverse usage patterns** (function calls, method calls, imports)
- **Real-world complexity** without being overwhelming

## Testing Strategy

1. **Start small** with Typer or similar (~10k LOC)
2. **Validate core functionality** with inheritance resolution
3. **Test import resolution** across multiple modules
4. **Scale up gradually** to larger codebases
5. **Compare results** against manual analysis for accuracy verification
