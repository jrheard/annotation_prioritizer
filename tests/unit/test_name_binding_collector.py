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

    # Verify bindings were collected (3 functions + 1 class)
    assert len(collector.bindings) == 4
    # Verify scope stack is restored to module level
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

    assert len(collector.bindings) == 2

    # First binding is the function itself
    func_binding = collector.bindings[0]
    assert func_binding.name == "process_data"
    assert func_binding.kind == NameBindingKind.FUNCTION

    # Second binding is the import inside the function
    import_binding = collector.bindings[1]
    assert import_binding.name == "pd"
    assert import_binding.line_number == 3
    # Scope stack should include the function
    assert len(import_binding.scope_stack) == 2
    assert import_binding.scope_stack[0].kind == ScopeKind.MODULE
    assert import_binding.scope_stack[1].kind == ScopeKind.FUNCTION
    assert import_binding.scope_stack[1].name == "process_data"


def test_import_in_class() -> None:
    """Imports inside classes track the class scope."""
    source = """
class DataProcessor:
    from typing import ClassVar
"""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 2

    # First binding is the class itself
    class_binding = collector.bindings[0]
    assert class_binding.name == "DataProcessor"
    assert class_binding.kind == NameBindingKind.CLASS

    # Second binding is the import inside the class
    import_binding = collector.bindings[1]
    assert import_binding.name == "ClassVar"
    assert len(import_binding.scope_stack) == 2
    assert import_binding.scope_stack[1].kind == ScopeKind.CLASS
    assert import_binding.scope_stack[1].name == "DataProcessor"


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


# Function binding collection tests


def test_module_level_function() -> None:
    """Module-level functions are tracked with qualified names."""
    source = """
def calculate(x, y):
    return x + y
"""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 1
    binding = collector.bindings[0]
    assert binding.name == "calculate"
    assert binding.line_number == 2
    assert binding.kind == NameBindingKind.FUNCTION
    assert binding.qualified_name == "__module__.calculate"
    assert binding.source_module is None
    assert binding.target_class is None
    assert len(binding.scope_stack) == 1
    assert binding.scope_stack[0].kind == ScopeKind.MODULE


def test_nested_function() -> None:
    """Nested functions track both outer and inner functions."""
    source = """
def outer():
    def inner():
        pass
"""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 2

    # Outer function
    outer_binding = collector.bindings[0]
    assert outer_binding.name == "outer"
    assert outer_binding.line_number == 2
    assert outer_binding.kind == NameBindingKind.FUNCTION
    assert outer_binding.qualified_name == "__module__.outer"
    assert len(outer_binding.scope_stack) == 1

    # Inner function
    inner_binding = collector.bindings[1]
    assert inner_binding.name == "inner"
    assert inner_binding.line_number == 3
    assert inner_binding.kind == NameBindingKind.FUNCTION
    assert inner_binding.qualified_name == "__module__.outer.inner"
    assert len(inner_binding.scope_stack) == 2
    assert inner_binding.scope_stack[0].kind == ScopeKind.MODULE
    assert inner_binding.scope_stack[1].kind == ScopeKind.FUNCTION
    assert inner_binding.scope_stack[1].name == "outer"


def test_class_method() -> None:
    """Class methods are tracked with the class in their scope."""
    source = """
class Calculator:
    def add(self, a, b):
        return a + b
"""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 2

    # First binding is the class itself
    class_binding = collector.bindings[0]
    assert class_binding.name == "Calculator"
    assert class_binding.line_number == 2
    assert class_binding.kind == NameBindingKind.CLASS
    assert class_binding.qualified_name == "__module__.Calculator"

    # Second binding is the method
    method_binding = collector.bindings[1]
    assert method_binding.name == "add"
    assert method_binding.line_number == 3
    assert method_binding.kind == NameBindingKind.FUNCTION
    assert method_binding.qualified_name == "__module__.Calculator.add"
    assert len(method_binding.scope_stack) == 2
    assert method_binding.scope_stack[0].kind == ScopeKind.MODULE
    assert method_binding.scope_stack[1].kind == ScopeKind.CLASS
    assert method_binding.scope_stack[1].name == "Calculator"


def test_async_function() -> None:
    """Async functions are tracked like regular functions."""
    source = """
async def fetch_data():
    pass
"""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 1
    binding = collector.bindings[0]
    assert binding.name == "fetch_data"
    assert binding.line_number == 2
    assert binding.kind == NameBindingKind.FUNCTION
    assert binding.qualified_name == "__module__.fetch_data"


def test_async_class_method() -> None:
    """Async class methods track the class scope."""
    source = """
class APIClient:
    async def fetch(self, url):
        pass
"""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 2

    # First binding is the class itself
    class_binding = collector.bindings[0]
    assert class_binding.name == "APIClient"
    assert class_binding.kind == NameBindingKind.CLASS

    # Second binding is the async method
    method_binding = collector.bindings[1]
    assert method_binding.name == "fetch"
    assert method_binding.kind == NameBindingKind.FUNCTION
    assert method_binding.qualified_name == "__module__.APIClient.fetch"
    assert len(method_binding.scope_stack) == 2
    assert method_binding.scope_stack[1].kind == ScopeKind.CLASS


def test_function_shadows_import() -> None:
    """Functions can shadow imports at the same scope level."""
    source = """
from math import sqrt
def sqrt(x):
    return x ** 0.5
"""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 2

    # Import comes first
    import_binding = collector.bindings[0]
    assert import_binding.name == "sqrt"
    assert import_binding.line_number == 2
    assert import_binding.kind == NameBindingKind.IMPORT

    # Function shadows it
    func_binding = collector.bindings[1]
    assert func_binding.name == "sqrt"
    assert func_binding.line_number == 3
    assert func_binding.kind == NameBindingKind.FUNCTION


def test_multiple_functions_same_scope() -> None:
    """Multiple functions in the same scope are all tracked."""
    source = """
def first():
    pass

def second():
    pass

def third():
    pass
"""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 3
    names = [b.name for b in collector.bindings]
    assert names == ["first", "second", "third"]
    line_numbers = [b.line_number for b in collector.bindings]
    assert line_numbers == [2, 5, 8]


def test_deeply_nested_functions() -> None:
    """Deeply nested functions build correct qualified names."""
    source = """
def level1():
    def level2():
        def level3():
            pass
"""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 3
    assert collector.bindings[0].qualified_name == "__module__.level1"
    assert collector.bindings[1].qualified_name == "__module__.level1.level2"
    assert collector.bindings[2].qualified_name == "__module__.level1.level2.level3"


def test_function_in_nested_class() -> None:
    """Functions inside nested classes track the full scope chain."""
    source = """
class Outer:
    class Inner:
        def method(self):
            pass
"""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 3

    # First binding is Outer class
    outer_binding = collector.bindings[0]
    assert outer_binding.name == "Outer"
    assert outer_binding.kind == NameBindingKind.CLASS

    # Second binding is Inner class
    inner_binding = collector.bindings[1]
    assert inner_binding.name == "Inner"
    assert inner_binding.kind == NameBindingKind.CLASS
    assert inner_binding.qualified_name == "__module__.Outer.Inner"

    # Third binding is the method
    method_binding = collector.bindings[2]
    assert method_binding.name == "method"
    assert method_binding.qualified_name == "__module__.Outer.Inner.method"
    assert len(method_binding.scope_stack) == 3
    assert method_binding.scope_stack[1].name == "Outer"
    assert method_binding.scope_stack[2].name == "Inner"


# Class binding collection tests


def test_top_level_class() -> None:
    """Top-level classes are tracked with qualified names."""
    source = """
class Calculator:
    pass
"""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 1
    binding = collector.bindings[0]
    assert binding.name == "Calculator"
    assert binding.line_number == 2
    assert binding.kind == NameBindingKind.CLASS
    assert binding.qualified_name == "__module__.Calculator"
    assert binding.source_module is None
    assert binding.target_class is None
    assert len(binding.scope_stack) == 1
    assert binding.scope_stack[0].kind == ScopeKind.MODULE


def test_nested_class() -> None:
    """Nested classes build correct qualified names."""
    source = """
class Outer:
    class Inner:
        pass
"""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 2

    # Outer class
    outer_binding = collector.bindings[0]
    assert outer_binding.name == "Outer"
    assert outer_binding.line_number == 2
    assert outer_binding.kind == NameBindingKind.CLASS
    assert outer_binding.qualified_name == "__module__.Outer"
    assert len(outer_binding.scope_stack) == 1

    # Inner class
    inner_binding = collector.bindings[1]
    assert inner_binding.name == "Inner"
    assert inner_binding.line_number == 3
    assert inner_binding.kind == NameBindingKind.CLASS
    assert inner_binding.qualified_name == "__module__.Outer.Inner"
    assert len(inner_binding.scope_stack) == 2
    assert inner_binding.scope_stack[0].kind == ScopeKind.MODULE
    assert inner_binding.scope_stack[1].kind == ScopeKind.CLASS
    assert inner_binding.scope_stack[1].name == "Outer"


def test_class_inside_function() -> None:
    """Classes defined inside functions track the function scope."""
    source = """
def create_class():
    class LocalClass:
        pass
    return LocalClass
"""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 2

    # Function binding
    func_binding = collector.bindings[0]
    assert func_binding.name == "create_class"
    assert func_binding.kind == NameBindingKind.FUNCTION

    # Class binding inside function
    class_binding = collector.bindings[1]
    assert class_binding.name == "LocalClass"
    assert class_binding.line_number == 3
    assert class_binding.kind == NameBindingKind.CLASS
    assert class_binding.qualified_name == "__module__.create_class.LocalClass"
    assert len(class_binding.scope_stack) == 2
    assert class_binding.scope_stack[0].kind == ScopeKind.MODULE
    assert class_binding.scope_stack[1].kind == ScopeKind.FUNCTION
    assert class_binding.scope_stack[1].name == "create_class"


def test_class_shadows_import() -> None:
    """Classes can shadow imports at the same scope level."""
    source = """
from typing import List
class List:
    pass
"""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 2

    # Import comes first
    import_binding = collector.bindings[0]
    assert import_binding.name == "List"
    assert import_binding.line_number == 2
    assert import_binding.kind == NameBindingKind.IMPORT

    # Class shadows it
    class_binding = collector.bindings[1]
    assert class_binding.name == "List"
    assert class_binding.line_number == 3
    assert class_binding.kind == NameBindingKind.CLASS


def test_multiple_classes_same_scope() -> None:
    """Multiple classes in the same scope are all tracked."""
    source = """
class First:
    pass

class Second:
    pass

class Third:
    pass
"""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 3
    names = [b.name for b in collector.bindings]
    assert names == ["First", "Second", "Third"]
    line_numbers = [b.line_number for b in collector.bindings]
    assert line_numbers == [2, 5, 8]
    assert all(b.kind == NameBindingKind.CLASS for b in collector.bindings)


def test_deeply_nested_classes() -> None:
    """Deeply nested classes build correct qualified names."""
    source = """
class Level1:
    class Level2:
        class Level3:
            pass
"""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 3
    assert collector.bindings[0].qualified_name == "__module__.Level1"
    assert collector.bindings[1].qualified_name == "__module__.Level1.Level2"
    assert collector.bindings[2].qualified_name == "__module__.Level1.Level2.Level3"


def test_class_with_multiple_methods() -> None:
    """Classes with multiple methods track all bindings."""
    source = """
class Calculator:
    def add(self, a, b):
        return a + b

    def subtract(self, a, b):
        return a - b

    async def multiply_async(self, a, b):
        return a * b
"""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 4

    # Class binding
    class_binding = collector.bindings[0]
    assert class_binding.name == "Calculator"
    assert class_binding.kind == NameBindingKind.CLASS

    # Method bindings
    method_names = [b.name for b in collector.bindings[1:]]
    assert method_names == ["add", "subtract", "multiply_async"]
    assert all(b.kind == NameBindingKind.FUNCTION for b in collector.bindings[1:])
    assert all(
        b.qualified_name is not None and b.qualified_name.startswith("__module__.Calculator.")
        for b in collector.bindings[1:]
    )


def test_class_in_nested_function() -> None:
    """Classes inside nested functions track the full scope chain."""
    source = """
def outer():
    def inner():
        class LocalClass:
            pass
"""
    tree = ast.parse(source)
    collector = NameBindingCollector()
    collector.visit(tree)

    assert len(collector.bindings) == 3

    # outer function
    assert collector.bindings[0].name == "outer"
    assert collector.bindings[0].kind == NameBindingKind.FUNCTION

    # inner function
    assert collector.bindings[1].name == "inner"
    assert collector.bindings[1].kind == NameBindingKind.FUNCTION

    # LocalClass
    class_binding = collector.bindings[2]
    assert class_binding.name == "LocalClass"
    assert class_binding.kind == NameBindingKind.CLASS
    assert class_binding.qualified_name == "__module__.outer.inner.LocalClass"
    assert len(class_binding.scope_stack) == 3
    assert class_binding.scope_stack[0].kind == ScopeKind.MODULE
    assert class_binding.scope_stack[1].kind == ScopeKind.FUNCTION
    assert class_binding.scope_stack[1].name == "outer"
    assert class_binding.scope_stack[2].kind == ScopeKind.FUNCTION
    assert class_binding.scope_stack[2].name == "inner"
