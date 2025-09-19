"""Unit tests for ClassDiscoveryVisitor and build_class_registry."""

import ast

import pytest

from annotation_prioritizer.ast_visitors.class_discovery import (
    ClassDiscoveryVisitor,
    ClassRegistry,
    build_class_registry,
)
from annotation_prioritizer.models import make_qualified_name


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

    # Check user-defined classes
    assert "__module__.MyClass" in registry.classes
    assert "__module__.AnotherClass" in registry.classes
    assert "__module__.AnotherClass.Nested" in registry.classes

    # Test is_class method
    assert registry.is_known_class(make_qualified_name("__module__.MyClass")) is True
    assert registry.is_known_class(make_qualified_name("__module__.AnotherClass")) is True
    assert registry.is_known_class(make_qualified_name("__module__.AnotherClass.Nested")) is True
    assert registry.is_known_class(make_qualified_name("NotAClass")) is False


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


def test_class_registry_identifies_user_classes() -> None:
    """Test that ClassRegistry correctly identifies user-defined classes."""
    registry = ClassRegistry(
        classes=frozenset(
            [
                make_qualified_name("__module__.Calculator"),
                make_qualified_name("__module__.Parser"),
            ]
        ),
    )
    assert registry.is_known_class(make_qualified_name("__module__.Calculator")) is True
    assert registry.is_known_class(make_qualified_name("__module__.Parser")) is True
    assert registry.is_known_class(make_qualified_name("MAX_SIZE")) is False
    assert registry.is_known_class(make_qualified_name("unknown")) is False
    assert registry.is_known_class(make_qualified_name("int")) is False  # Builtins not tracked


def test_class_registry_merge() -> None:
    """Test merging two ClassRegistry instances."""
    registry1 = ClassRegistry(classes=frozenset([make_qualified_name("__module__.ClassA")]))
    registry2 = ClassRegistry(classes=frozenset([make_qualified_name("__module__.ClassB")]))
    merged = registry1.merge(registry2)
    assert merged.is_known_class(make_qualified_name("__module__.ClassA")) is True
    assert merged.is_known_class(make_qualified_name("__module__.ClassB")) is True


def test_class_registry_empty() -> None:
    """Test ClassRegistry with empty sets."""
    registry = ClassRegistry(classes=frozenset())
    assert registry.is_known_class(make_qualified_name("anything")) is False
    assert registry.is_known_class(make_qualified_name("")) is False


def test_user_defined_class_shadows_builtin() -> None:
    """Test that user-defined classes with builtin names are tracked."""
    source = """
# User defines their own 'int' class
class int:
    def __init__(self, value):
        self.value = value

# User defines their own 'list' class
class list:
    @staticmethod
    def append(item):
        pass
"""
    tree = ast.parse(source)
    registry = build_class_registry(tree)

    # User-defined classes are tracked
    assert registry.is_known_class(make_qualified_name("__module__.int")) is True
    assert registry.is_known_class(make_qualified_name("__module__.list")) is True

    # But builtin 'int' and 'list' are NOT tracked
    assert registry.is_known_class(make_qualified_name("int")) is False
    assert registry.is_known_class(make_qualified_name("list")) is False
