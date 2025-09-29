"""Unit tests for NameBindingCollector."""

import ast

import pytest

from annotation_prioritizer.ast_visitors.name_binding_collector import NameBindingCollector
from annotation_prioritizer.models import NameBindingKind, ScopeKind


def test_initial_state() -> None:
    """Collector starts with empty bindings and module scope."""
    collector = NameBindingCollector()

    assert collector.bindings == []
    assert collector.unresolved_variables == []
    assert len(collector.scope_stack) == 1
    assert collector.scope_stack[0].kind == ScopeKind.MODULE


def test_scope_restored_after_traversal() -> None:
    """Scope stack returns to module level after visiting nested structures."""
    source = """
def first():
    pass

class Calculator:
    def add(self):
        pass

async def fetch():
    pass
"""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.scope_stack) == 1
    assert collector.scope_stack[0].kind == ScopeKind.MODULE


# Import binding collection tests


def test_simple_module_import() -> None:
    """Simple module imports like 'import math' are tracked."""
    source = "import math"
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 1
    binding = collector.bindings[0]
    assert binding.name == "math"
    assert binding.line_number == 1
    assert binding.kind == NameBindingKind.IMPORT
    assert binding.qualified_name is None
    assert binding.source_module == "math"
    assert binding.target_class is None


def test_aliased_module_import() -> None:
    """Aliased imports like 'import numpy as np' use the alias name."""
    source = "import numpy as np"
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 1
    binding = collector.bindings[0]
    assert binding.name == "np"
    assert binding.source_module == "numpy"
    assert binding.kind == NameBindingKind.IMPORT


def test_multiple_module_imports() -> None:
    """Multiple imports in one statement create separate bindings."""
    source = "import math, os, sys"
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 3
    names = [b.name for b in collector.bindings]
    assert names == ["math", "os", "sys"]
    assert all(b.kind == NameBindingKind.IMPORT for b in collector.bindings)
    assert all(b.source_module == b.name for b in collector.bindings)


def test_simple_from_import() -> None:
    """From imports like 'from math import sqrt' track the imported name."""
    source = "from math import sqrt"
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 1
    binding = collector.bindings[0]
    assert binding.name == "sqrt"
    assert binding.line_number == 1
    assert binding.kind == NameBindingKind.IMPORT
    assert binding.source_module == "math"


def test_aliased_from_import() -> None:
    """Aliased from imports use the alias as the binding name."""
    source = "from math import sqrt as square_root"
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 1
    binding = collector.bindings[0]
    assert binding.name == "square_root"
    assert binding.source_module == "math"


def test_multiple_from_imports() -> None:
    """Multiple names in from imports create separate bindings."""
    source = "from math import sqrt, cos, sin"
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 3
    names = [b.name for b in collector.bindings]
    assert names == ["sqrt", "cos", "sin"]
    assert all(b.source_module == "math" for b in collector.bindings)


def test_star_import() -> None:
    """Star imports are tracked with '*' as the name."""
    source = "from math import *"
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 1
    binding = collector.bindings[0]
    assert binding.name == "*"
    assert binding.source_module == "math"


def test_relative_imports() -> None:
    """Relative imports track the module correctly."""
    source = """
from . import utils
from .. import parent
from ...package import module
"""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 3
    # Pure relative imports have None as module in AST
    assert collector.bindings[0].name == "utils"
    assert collector.bindings[0].source_module is None
    assert collector.bindings[1].name == "parent"
    assert collector.bindings[1].source_module is None
    # Relative import with package name has the package as module
    assert collector.bindings[2].name == "module"
    assert collector.bindings[2].source_module == "package"


def test_import_in_function() -> None:
    """Imports inside functions track the function scope."""
    source = """
def process_data():
    import pandas as pd
    return pd
"""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 1
    binding = collector.bindings[0]
    assert binding.name == "pd"
    assert binding.line_number == 3
    # Scope stack should include the function
    assert len(binding.scope_stack) == 2
    assert binding.scope_stack[0].kind == ScopeKind.MODULE
    assert binding.scope_stack[1].kind == ScopeKind.FUNCTION
    assert binding.scope_stack[1].name == "process_data"


def test_import_in_class() -> None:
    """Imports inside classes track the class scope."""
    source = """
class DataProcessor:
    from typing import ClassVar
"""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 1
    binding = collector.bindings[0]
    assert binding.name == "ClassVar"
    assert len(binding.scope_stack) == 2
    assert binding.scope_stack[1].kind == ScopeKind.CLASS
    assert binding.scope_stack[1].name == "DataProcessor"


@pytest.mark.parametrize(
    ("source", "expected_count", "expected_names"),
    [
        ("import math", 1, ["math"]),
        ("import math, os", 2, ["math", "os"]),
        ("from math import sqrt", 1, ["sqrt"]),
        ("from math import sqrt, cos", 2, ["sqrt", "cos"]),
        ("import numpy as np", 1, ["np"]),
        ("from math import sqrt as sq", 1, ["sq"]),
    ],
)
def test_import_patterns(source: str, expected_count: int, expected_names: list[str]) -> None:
    """Various import patterns are tracked correctly."""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == expected_count
    names = [b.name for b in collector.bindings]
    assert names == expected_names


def test_multiple_imports_track_line_numbers() -> None:
    """Each import statement tracks its own line number."""
    source = """
import math
from os import path
import sys
"""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 3
    assert collector.bindings[0].line_number == 2
    assert collector.bindings[1].line_number == 3
    assert collector.bindings[2].line_number == 4
