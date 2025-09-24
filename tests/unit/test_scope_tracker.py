"""Unit tests for the scope_tracker module.

Tests cover the pure functions for scope stack management and name resolution
during AST traversal.
"""

import ast

import pytest

from annotation_prioritizer.models import Scope, ScopeKind, make_qualified_name
from annotation_prioritizer.scope_tracker import (
    _generate_name_candidates,  # pyright: ignore[reportPrivateUsage]
    add_scope,
    build_qualified_name,
    create_initial_stack,
    drop_last_scope,
    extract_attribute_chain,
    resolve_name_in_scope,
)


def test_create_initial_stack() -> None:
    """Test that create_initial_stack creates a stack with module scope."""
    stack = create_initial_stack()
    assert len(stack) == 1
    assert stack[0] == Scope(kind=ScopeKind.MODULE, name="__module__")


def test_add_drop_scope() -> None:
    """Test adding and dropping scopes from the stack."""
    stack = create_initial_stack()

    # Push a class scope
    class_scope = Scope(kind=ScopeKind.CLASS, name="MyClass")
    stack = add_scope(stack, class_scope)
    assert len(stack) == 2
    assert stack[-1] == class_scope

    # Push a function scope
    func_scope = Scope(kind=ScopeKind.FUNCTION, name="my_method")
    stack = add_scope(stack, func_scope)
    assert len(stack) == 3
    assert stack[-1] == func_scope

    # Pop function scope
    stack = drop_last_scope(stack)
    assert len(stack) == 2
    assert stack[-1] == class_scope

    # Pop class scope
    stack = drop_last_scope(stack)
    assert len(stack) == 1
    assert stack[-1] == Scope(kind=ScopeKind.MODULE, name="__module__")


def test_cannot_drop_module_scope() -> None:
    """Test that module scope cannot be dropped."""
    stack = create_initial_stack()
    with pytest.raises(AssertionError, match="Cannot pop module scope"):
        drop_last_scope(stack)


def test_stack_is_immutable() -> None:
    """Test that the stack is immutable (tuple)."""
    stack = create_initial_stack()
    assert isinstance(stack, tuple)
    # Operations return new stacks
    new_stack = add_scope(stack, Scope(kind=ScopeKind.CLASS, name="Test"))
    assert stack != new_stack
    assert len(stack) == 1
    assert len(new_stack) == 2


def test_complex_nesting() -> None:
    """Test complex nesting scenarios with all scope types."""
    stack = create_initial_stack()

    # Build: module -> class -> function -> class -> function
    stack = add_scope(stack, Scope(kind=ScopeKind.CLASS, name="OuterClass"))
    stack = add_scope(stack, Scope(kind=ScopeKind.FUNCTION, name="outer_method"))
    stack = add_scope(stack, Scope(kind=ScopeKind.CLASS, name="LocalClass"))
    stack = add_scope(stack, Scope(kind=ScopeKind.FUNCTION, name="local_method"))

    # Check that the stack has all expected scopes
    assert len(stack) == 5
    assert stack[0].name == "__module__"
    assert stack[1].name == "OuterClass"
    assert stack[2].name == "outer_method"
    assert stack[3].name == "LocalClass"
    assert stack[4].name == "local_method"


@pytest.mark.parametrize(
    ("scope_stack", "name", "expected"),
    [
        # Module level only
        (
            (Scope(kind=ScopeKind.MODULE, name="__module__"),),
            "foo",
            ("__module__.foo",),
        ),
        # Module + class
        (
            (
                Scope(kind=ScopeKind.MODULE, name="__module__"),
                Scope(kind=ScopeKind.CLASS, name="MyClass"),
            ),
            "method",
            ("__module__.MyClass.method", "__module__.method"),
        ),
        # Module + class + function
        (
            (
                Scope(kind=ScopeKind.MODULE, name="__module__"),
                Scope(kind=ScopeKind.CLASS, name="MyClass"),
                Scope(kind=ScopeKind.FUNCTION, name="helper"),
            ),
            "inner",
            (
                "__module__.MyClass.helper.inner",
                "__module__.MyClass.inner",
                "__module__.inner",
            ),
        ),
        # Compound name
        (
            (
                Scope(kind=ScopeKind.MODULE, name="__module__"),
                Scope(kind=ScopeKind.CLASS, name="Outer"),
            ),
            "Inner.method",
            ("__module__.Outer.Inner.method", "__module__.Inner.method"),
        ),
    ],
)
def test_generate_name_candidates(
    scope_stack: tuple[Scope, ...], name: str, expected: tuple[str, ...]
) -> None:
    """Test generation of qualified name candidates from scope stack."""
    result = _generate_name_candidates(scope_stack, name)
    assert result == expected


def test_build_qualified_name_basic() -> None:
    """Test building qualified names from scope stack and name."""
    scope_stack = (
        Scope(kind=ScopeKind.MODULE, name="__module__"),
        Scope(kind=ScopeKind.CLASS, name="Calculator"),
        Scope(kind=ScopeKind.FUNCTION, name="helper"),
    )
    result = build_qualified_name(scope_stack, "add")
    assert result == "__module__.Calculator.helper.add"


def test_build_qualified_name_nested() -> None:
    """Test building qualified names with nested scopes."""
    scope_stack = (
        Scope(kind=ScopeKind.MODULE, name="__module__"),
        Scope(kind=ScopeKind.CLASS, name="Outer"),
        Scope(kind=ScopeKind.FUNCTION, name="method"),
        Scope(kind=ScopeKind.CLASS, name="Inner"),
    )
    result = build_qualified_name(scope_stack, "foo")
    assert result == "__module__.Outer.method.Inner.foo"


def test_build_qualified_name_validation_errors() -> None:
    """Test validation errors in build_qualified_name."""
    # Empty scope stack
    with pytest.raises(ValueError, match="Cannot build qualified name from empty scope stack"):
        build_qualified_name((), "foo")

    # Empty name string
    scope_stack = (Scope(kind=ScopeKind.MODULE, name="__module__"),)
    with pytest.raises(ValueError, match="Name cannot be empty or whitespace"):
        build_qualified_name(scope_stack, "  ")


def test_resolve_name_in_scope() -> None:
    """Test resolving names to qualified forms by checking scope levels."""
    scope_stack = (
        Scope(kind=ScopeKind.MODULE, name="__module__"),
        Scope(kind=ScopeKind.CLASS, name="Outer"),
        Scope(kind=ScopeKind.FUNCTION, name="method"),
    )
    registry = frozenset(
        {
            make_qualified_name("__module__.Outer.method.Helper"),
            make_qualified_name("__module__.Outer.Helper"),
            make_qualified_name("__module__.Helper"),
            make_qualified_name("__module__.other_func"),
        }
    )

    # Test resolution finds innermost match first
    result = resolve_name_in_scope(scope_stack, "Helper", registry)
    assert result == make_qualified_name("__module__.Outer.method.Helper")

    # Test resolution with name not in registry
    result = resolve_name_in_scope(scope_stack, "NotFound", registry)
    assert result is None

    # Test resolution with compound name
    registry_with_compound = frozenset(
        {
            make_qualified_name("__module__.Outer.Inner.method"),
            make_qualified_name("__module__.Inner.method"),
        }
    )
    result = resolve_name_in_scope(scope_stack, "Inner.method", registry_with_compound)
    assert result == make_qualified_name("__module__.Outer.Inner.method")


def test_extract_attribute_chain_simple_attribute() -> None:
    """Test extracting attribute chain from simple attribute access."""
    # Create AST for: obj.attr
    code = "obj.attr"
    tree = ast.parse(code, mode="eval")
    attr_node = tree.body
    assert isinstance(attr_node, ast.Attribute)

    result = extract_attribute_chain(attr_node)
    assert result == ("obj", "attr")


def test_extract_attribute_chain_nested_attributes() -> None:
    """Test extracting attribute chain from nested attribute access."""
    # Create AST for: Outer.Middle.Inner
    code = "Outer.Middle.Inner"
    tree = ast.parse(code, mode="eval")
    attr_node = tree.body
    assert isinstance(attr_node, ast.Attribute)

    result = extract_attribute_chain(attr_node)
    assert result == ("Outer", "Middle", "Inner")


def test_extract_attribute_chain_deep_nesting() -> None:
    """Test extracting attribute chain from deeply nested attributes."""
    # Create AST for: A.B.C.D.E
    code = "A.B.C.D.E"
    tree = ast.parse(code, mode="eval")
    attr_node = tree.body
    assert isinstance(attr_node, ast.Attribute)

    result = extract_attribute_chain(attr_node)
    assert result == ("A", "B", "C", "D", "E")


def test_extract_attribute_chain_single_level() -> None:
    """Test extracting attribute chain with just one level (Name.attr)."""
    # This specifically tests lines 202-203 where we handle ast.Name
    code = "MyClass.method"
    tree = ast.parse(code, mode="eval")
    attr_node = tree.body
    assert isinstance(attr_node, ast.Attribute)

    result = extract_attribute_chain(attr_node)
    assert result == ("MyClass", "method")


def test_extract_attribute_chain_from_call() -> None:
    """Test extracting attribute chain from a method call's function attribute."""
    # Create AST for: obj.method() and extract the function part
    code = "obj.method()"
    tree = ast.parse(code, mode="eval")
    call_node = tree.body
    assert isinstance(call_node, ast.Call)
    assert isinstance(call_node.func, ast.Attribute)

    result = extract_attribute_chain(call_node.func)
    assert result == ("obj", "method")


def test_extract_attribute_chain_edge_case_with_expression() -> None:
    """Test that extract_attribute_chain raises assertion for unsupported expressions."""
    tree = ast.parse("(a + b).method", mode="eval")
    assert isinstance(tree.body, ast.Attribute)  # Type narrowing for pyright
    attr_node = tree.body  # This is the Attribute node with BinOp as value

    with pytest.raises(AssertionError, match=r"Expected ast\.Name at base of attribute chain"):
        extract_attribute_chain(attr_node)


@pytest.mark.parametrize(
    ("code", "expected_chain"),
    [
        ("x.y", ("x", "y")),
        ("self.helper", ("self", "helper")),
        ("cls.from_string", ("cls", "from_string")),
        ("module.submodule.function", ("module", "submodule", "function")),
        ("Path.home", ("Path", "home")),
    ],
)
def test_extract_attribute_chain_various_names(code: str, expected_chain: tuple[str, ...]) -> None:
    """Test extracting attribute chains with various naming patterns."""
    tree = ast.parse(code, mode="eval")
    attr_node = tree.body
    assert isinstance(attr_node, ast.Attribute)

    result = extract_attribute_chain(attr_node)
    assert result == expected_chain
