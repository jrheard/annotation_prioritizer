"""Unit tests for ClassDiscoveryVisitor and build_class_registry."""

import ast

import pytest

from annotation_prioritizer.class_discovery import (
    PYTHON_BUILTIN_TYPES,
    ClassDiscoveryVisitor,
    ClassRegistry,
    build_class_registry,
)


@pytest.mark.parametrize(
    ("source_code", "expected_classes"),
    [
        # Simple class
        (
            """
class Calculator:
    pass
""",
            ["__module__.Calculator"],
        ),
        # Multiple classes
        (
            """
class Calculator:
    pass

class Parser:
    pass
""",
            ["__module__.Calculator", "__module__.Parser"],
        ),
        # Nested class
        (
            """
class Outer:
    class Inner:
        pass
""",
            ["__module__.Outer", "__module__.Outer.Inner"],
        ),
        # Deeply nested classes
        (
            """
class Outer:
    class Middle:
        class Inner:
            pass
""",
            ["__module__.Outer", "__module__.Outer.Middle", "__module__.Outer.Middle.Inner"],
        ),
        # Non-PEP8 names
        (
            """
class xmlParser:
    pass
class dataProcessor:
    pass
""",
            ["__module__.xmlParser", "__module__.dataProcessor"],
        ),
        # Class in function (edge case)
        (
            """
def factory():
    class LocalClass:
        pass
    return LocalClass
""",
            ["__module__.factory.LocalClass"],
        ),
        # Class in async function
        (
            """
async def async_factory():
    class AsyncLocal:
        pass
    return AsyncLocal
""",
            ["__module__.async_factory.AsyncLocal"],
        ),
        # Multiple nested contexts
        (
            """
class Outer:
    def method(self):
        class MethodClass:
            pass
        return MethodClass

    class Inner:
        pass
""",
            ["__module__.Outer", "__module__.Outer.method.MethodClass", "__module__.Outer.Inner"],
        ),
        # Empty file (no classes)
        ("", []),
        # Only functions, no classes
        (
            """
def func1():
    pass

def func2():
    return 42
""",
            [],
        ),
    ],
)
def test_class_discovery_visitor(source_code: str, expected_classes: list[str]) -> None:
    """Test that ClassDiscoveryVisitor finds all class definitions."""
    tree = ast.parse(source_code)
    visitor = ClassDiscoveryVisitor()
    visitor.visit(tree)
    assert sorted(visitor.class_names) == sorted(expected_classes)


def test_build_class_registry() -> None:
    """Test that build_class_registry creates a complete registry."""
    source = """
class MyClass:
    pass

class AnotherClass:
    class Nested:
        pass
"""
    tree = ast.parse(source)
    registry = build_class_registry(tree)

    # Check AST classes
    assert "__module__.MyClass" in registry.ast_classes
    assert "__module__.AnotherClass" in registry.ast_classes
    assert "__module__.AnotherClass.Nested" in registry.ast_classes

    # Check builtin classes are included
    assert "int" in registry.builtin_classes
    assert "str" in registry.builtin_classes

    # Test is_class method
    assert registry.is_class("__module__.MyClass") is True
    assert registry.is_class("__module__.AnotherClass") is True
    assert registry.is_class("__module__.AnotherClass.Nested") is True
    assert registry.is_class("int") is True
    assert registry.is_class("str") is True
    assert registry.is_class("NotAClass") is False


def test_class_discovery_preserves_order() -> None:
    """Test that class discovery maintains definition order."""
    source = """
class First:
    pass

class Second:
    pass

class Third:
    pass
"""
    tree = ast.parse(source)
    visitor = ClassDiscoveryVisitor()
    visitor.visit(tree)
    assert visitor.class_names == ["__module__.First", "__module__.Second", "__module__.Third"]


def test_class_with_bases_and_decorators() -> None:
    """Test that classes with bases and decorators are still discovered."""
    source = """
@decorator
class Decorated:
    pass

class Child(Parent):
    pass

class MultiBase(Base1, Base2):
    pass
"""
    tree = ast.parse(source)
    visitor = ClassDiscoveryVisitor()
    visitor.visit(tree)
    assert "__module__.Decorated" in visitor.class_names
    assert "__module__.Child" in visitor.class_names
    assert "__module__.MultiBase" in visitor.class_names


def test_class_registry_identifies_ast_classes() -> None:
    """Test that ClassRegistry correctly identifies AST classes."""
    registry = ClassRegistry(
        ast_classes=frozenset(["__module__.Calculator", "__module__.Parser"]),
        builtin_classes=frozenset(["int", "str"]),
    )
    assert registry.is_class("__module__.Calculator") is True
    assert registry.is_class("int") is True
    assert registry.is_class("MAX_SIZE") is False
    assert registry.is_class("unknown") is False


def test_class_registry_identifies_builtin_classes() -> None:
    """Test that ClassRegistry correctly identifies built-in classes."""
    registry = ClassRegistry(
        ast_classes=frozenset(), builtin_classes=frozenset(["int", "str", "list", "dict"])
    )
    assert registry.is_class("int") is True
    assert registry.is_class("str") is True
    assert registry.is_class("list") is True
    assert registry.is_class("dict") is True
    assert registry.is_class("NotABuiltin") is False


def test_class_registry_merge() -> None:
    """Test merging two ClassRegistry instances."""
    registry1 = ClassRegistry(
        ast_classes=frozenset(["__module__.ClassA"]), builtin_classes=PYTHON_BUILTIN_TYPES
    )
    registry2 = ClassRegistry(
        ast_classes=frozenset(["__module__.ClassB"]), builtin_classes=PYTHON_BUILTIN_TYPES
    )
    merged = registry1.merge(registry2)
    assert merged.is_class("__module__.ClassA") is True
    assert merged.is_class("__module__.ClassB") is True
    # Built-ins should still be present
    assert merged.is_class("int") is True


def test_python_builtin_types_comprehensive() -> None:
    """Test that PYTHON_BUILTIN_TYPES includes expected built-in types."""
    # Check common built-in types
    assert "int" in PYTHON_BUILTIN_TYPES
    assert "str" in PYTHON_BUILTIN_TYPES
    assert "list" in PYTHON_BUILTIN_TYPES
    assert "dict" in PYTHON_BUILTIN_TYPES
    assert "tuple" in PYTHON_BUILTIN_TYPES
    assert "set" in PYTHON_BUILTIN_TYPES
    assert "frozenset" in PYTHON_BUILTIN_TYPES
    assert "bool" in PYTHON_BUILTIN_TYPES
    assert "float" in PYTHON_BUILTIN_TYPES
    assert "complex" in PYTHON_BUILTIN_TYPES
    assert "bytes" in PYTHON_BUILTIN_TYPES
    assert "bytearray" in PYTHON_BUILTIN_TYPES

    # Check exceptions are included
    assert "Exception" in PYTHON_BUILTIN_TYPES
    assert "ValueError" in PYTHON_BUILTIN_TYPES
    assert "TypeError" in PYTHON_BUILTIN_TYPES
    assert "KeyError" in PYTHON_BUILTIN_TYPES

    # Check that non-types are not included
    assert "print" not in PYTHON_BUILTIN_TYPES  # function, not type
    assert "len" not in PYTHON_BUILTIN_TYPES  # function, not type
    assert "None" not in PYTHON_BUILTIN_TYPES  # None is not a type
    assert "__name__" not in PYTHON_BUILTIN_TYPES  # string, not type


def test_class_registry_empty() -> None:
    """Test ClassRegistry with empty sets."""
    registry = ClassRegistry(ast_classes=frozenset(), builtin_classes=frozenset())
    assert registry.is_class("anything") is False
    assert registry.is_class("") is False
