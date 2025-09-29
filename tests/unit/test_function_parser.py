"""Unit tests for function_parser module."""

import ast
from pathlib import Path

from annotation_prioritizer.ast_visitors.function_parser import (
    FunctionDefinitionVisitor,
    generate_synthetic_init_methods,
)
from annotation_prioritizer.models import make_qualified_name
from tests.helpers.function_parsing import build_position_index_from_source, parse_functions_from_source


def test_class_with_explicit_init() -> None:
    """Classes with explicit __init__ don't get synthetic ones."""
    source = """
class Calculator:
    def __init__(self, x: int) -> None:
        self.x = x
"""
    # Parse functions using helper
    functions = parse_functions_from_source(source)

    # Should have exactly one __init__ (the explicit one)
    init_funcs = [f for f in functions if f.name == "__init__"]
    assert len(init_funcs) == 1
    assert init_funcs[0].qualified_name == make_qualified_name("__module__.Calculator.__init__")
    assert init_funcs[0].line_number == 3  # Line of the explicit __init__

    # The explicit __init__ should have parameters x and self
    param_names = [p.name for p in init_funcs[0].parameters]
    assert "self" in param_names
    assert "x" in param_names


def test_class_without_init() -> None:
    """Classes without __init__ get synthetic ones."""
    source = """
class SimpleClass:
    pass
"""
    # Parse functions (should create synthetic __init__)
    functions = parse_functions_from_source(source)

    # Should have exactly one function (the synthetic __init__)
    assert len(functions) == 1
    assert functions[0].name == "__init__"
    assert functions[0].qualified_name == make_qualified_name("__module__.SimpleClass.__init__")
    assert functions[0].line_number == 0  # Synthetic methods use line 0

    # Should have only self parameter
    assert len(functions[0].parameters) == 1
    assert functions[0].parameters[0].name == "self"
    assert not functions[0].parameters[0].has_annotation
    assert not functions[0].has_return_annotation


def test_multiple_classes_mixed() -> None:
    """Mix of classes with and without __init__."""
    source = """
class WithInit:
    def __init__(self):
        pass

class WithoutInit:
    pass

class AlsoWithInit:
    def __init__(self, x: int):
        self.x = x
"""
    functions = parse_functions_from_source(source)

    # Should have 3 __init__ methods total
    init_funcs = [f for f in functions if f.name == "__init__"]
    assert len(init_funcs) == 3

    # Check each one
    init_map = {str(f.qualified_name): f for f in init_funcs}

    # WithInit has explicit __init__
    with_init = init_map["__module__.WithInit.__init__"]
    assert with_init.line_number == 3  # Explicit line

    # WithoutInit has synthetic __init__
    without_init = init_map["__module__.WithoutInit.__init__"]
    assert without_init.line_number == 0  # Synthetic
    assert len(without_init.parameters) == 1
    assert without_init.parameters[0].name == "self"

    # AlsoWithInit has explicit __init__
    also_with = init_map["__module__.AlsoWithInit.__init__"]
    assert also_with.line_number == 10  # Explicit line


def test_nested_classes() -> None:
    """Nested classes get correct qualified names for synthetic __init__."""
    source = """
class Outer:
    class Inner:
        pass

    class InnerWithInit:
        def __init__(self):
            pass
"""
    functions = parse_functions_from_source(source)

    init_funcs = [f for f in functions if f.name == "__init__"]
    init_names = {str(f.qualified_name) for f in init_funcs}

    # Outer gets synthetic, Inner gets synthetic, InnerWithInit has explicit
    assert "__module__.Outer.__init__" in init_names
    assert "__module__.Outer.Inner.__init__" in init_names
    assert "__module__.Outer.InnerWithInit.__init__" in init_names

    # Check synthetic vs explicit
    for f in init_funcs:
        if "InnerWithInit" in str(f.qualified_name):
            assert f.line_number > 0  # Explicit
        else:
            assert f.line_number == 0  # Synthetic


def test_class_inside_function() -> None:
    """Classes inside functions get synthetic __init__ correctly."""
    source = """
def factory():
    class LocalClass:
        pass
    return LocalClass
"""
    functions = parse_functions_from_source(source)

    # Should have factory function and synthetic __init__
    func_names = [f.name for f in functions]
    assert "factory" in func_names
    assert "__init__" in func_names

    # Find the synthetic __init__
    init_func = next(f for f in functions if f.name == "__init__")
    assert init_func.qualified_name == make_qualified_name("__module__.factory.LocalClass.__init__")
    assert init_func.line_number == 0


def test_generate_synthetic_init_methods_directly() -> None:
    """Test generate_synthetic_init_methods function directly."""
    source = """
class A:
    pass

class B:
    def __init__(self):
        pass
"""
    tree = ast.parse(source)
    _, position_index, _ = build_position_index_from_source(source)
    file_path = Path("test.py")

    # First get the existing functions (just B.__init__)
    visitor = FunctionDefinitionVisitor(file_path)
    visitor.visit(tree)
    known_functions = tuple(visitor.functions)

    # Generate synthetic __init__ methods
    synthetic_inits = generate_synthetic_init_methods(known_functions, position_index, file_path)

    # Should only generate one for A (B already has __init__)
    assert len(synthetic_inits) == 1
    assert synthetic_inits[0].qualified_name == make_qualified_name("__module__.A.__init__")
    assert synthetic_inits[0].line_number == 0


def test_synthetic_init_parameters() -> None:
    """Synthetic __init__ methods have correct parameter structure."""
    source = """
class TestClass:
    pass
"""
    functions = parse_functions_from_source(source)

    # Get the synthetic __init__
    init_func = functions[0]
    assert init_func.name == "__init__"

    # Verify parameter details
    assert len(init_func.parameters) == 1
    param = init_func.parameters[0]
    assert param.name == "self"
    assert param.has_annotation is False
    assert param.is_variadic is False
    assert param.is_keyword is False

    # Verify no return annotation
    assert init_func.has_return_annotation is False


def test_empty_file() -> None:
    """Files with no classes generate no synthetic __init__ methods."""
    source = """
def some_function():
    pass
"""
    functions = parse_functions_from_source(source)

    # Should only have some_function, no __init__
    assert len(functions) == 1
    assert functions[0].name == "some_function"
