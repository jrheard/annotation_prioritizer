"""Unit tests for the scope_tracker module.

Tests cover the ScopeState class and pure helper functions for scope tracking
and name resolution during AST traversal.
"""

import ast

import pytest

from annotation_prioritizer.models import Scope, ScopeKind
from annotation_prioritizer.scope_tracker import (
    ScopeState,
    build_qualified_name,
    extract_attribute_chain,
    find_first_match,
    generate_name_candidates,
)


def test_scope_state_initialization() -> None:
    """Test that ScopeState initializes with module scope."""
    state = ScopeState()
    assert len(state.stack) == 1
    assert state.current_scope == Scope(kind=ScopeKind.MODULE, name="__module__")


def test_scope_state_push_pop() -> None:
    """Test pushing and popping scopes from the stack."""
    state = ScopeState()

    # Push a class scope
    class_scope = Scope(kind=ScopeKind.CLASS, name="MyClass")
    state.push(class_scope)
    assert len(state.stack) == 2
    assert state.current_scope == class_scope

    # Push a function scope
    func_scope = Scope(kind=ScopeKind.FUNCTION, name="my_method")
    state.push(func_scope)
    assert len(state.stack) == 3
    assert state.current_scope == func_scope

    # Pop function scope
    state.pop()
    assert len(state.stack) == 2
    assert state.current_scope == class_scope

    # Pop class scope
    state.pop()
    assert len(state.stack) == 1
    assert state.current_scope == Scope(kind=ScopeKind.MODULE, name="__module__")


def test_scope_state_cannot_pop_module() -> None:
    """Test that module scope cannot be popped."""
    state = ScopeState()
    with pytest.raises(AssertionError, match="Cannot pop module scope"):
        state.pop()


def test_scope_state_stack_immutable() -> None:
    """Test that the stack property returns an immutable tuple."""
    state = ScopeState()
    stack = state.stack
    assert isinstance(stack, tuple)
    # Verify we can't modify the returned tuple
    assert stack == (Scope(kind=ScopeKind.MODULE, name="__module__"),)


def test_scope_state_get_containing_class_no_class() -> None:
    """Test get_containing_class when not inside any class."""
    state = ScopeState()
    # Just module scope
    assert state.get_containing_class() is None

    # Module + function scope
    state.push(Scope(kind=ScopeKind.FUNCTION, name="standalone_func"))
    assert state.get_containing_class() is None


def test_scope_state_get_containing_class_single_class() -> None:
    """Test get_containing_class with a single class in the stack."""
    state = ScopeState()
    state.push(Scope(kind=ScopeKind.CLASS, name="MyClass"))
    assert state.get_containing_class() == "__module__.MyClass"

    # Add a function inside the class
    state.push(Scope(kind=ScopeKind.FUNCTION, name="method"))
    assert state.get_containing_class() == "__module__.MyClass"


def test_scope_state_get_containing_class_nested_classes() -> None:
    """Test get_containing_class with nested classes."""
    state = ScopeState()
    state.push(Scope(kind=ScopeKind.CLASS, name="Outer"))
    assert state.get_containing_class() == "__module__.Outer"

    state.push(Scope(kind=ScopeKind.CLASS, name="Inner"))
    assert state.get_containing_class() == "__module__.Outer.Inner"

    # Add a method in the inner class
    state.push(Scope(kind=ScopeKind.FUNCTION, name="inner_method"))
    assert state.get_containing_class() == "__module__.Outer.Inner"


def test_scope_state_get_containing_class_function_then_class() -> None:
    """Test get_containing_class when class is defined inside a function."""
    state = ScopeState()
    state.push(Scope(kind=ScopeKind.FUNCTION, name="factory"))
    state.push(Scope(kind=ScopeKind.CLASS, name="LocalClass"))
    assert state.get_containing_class() == "__module__.factory.LocalClass"


def test_scope_state_in_class() -> None:
    """Test in_class method for checking if inside a class."""
    state = ScopeState()
    # Initially not in class
    assert state.in_class() is False

    # Add a class
    state.push(Scope(kind=ScopeKind.CLASS, name="MyClass"))
    assert state.in_class() is True

    # Add a function inside the class
    state.push(Scope(kind=ScopeKind.FUNCTION, name="method"))
    assert state.in_class() is True

    # Pop the function, still in class
    state.pop()
    assert state.in_class() is True

    # Pop the class, no longer in class
    state.pop()
    assert state.in_class() is False


def test_scope_state_in_function() -> None:
    """Test in_function method for checking if inside a function."""
    state = ScopeState()
    # Initially not in function
    assert state.in_function() is False

    # Add a function
    state.push(Scope(kind=ScopeKind.FUNCTION, name="my_func"))
    assert state.in_function() is True

    # Add a class inside the function
    state.push(Scope(kind=ScopeKind.CLASS, name="LocalClass"))
    assert state.in_function() is True

    # Pop the class, still in function
    state.pop()
    assert state.in_function() is True

    # Pop the function, no longer in function
    state.pop()
    assert state.in_function() is False


def test_scope_state_complex_nesting() -> None:
    """Test complex nesting scenarios with all scope types."""
    state = ScopeState()

    # Build: module -> class -> function -> class -> function
    state.push(Scope(kind=ScopeKind.CLASS, name="OuterClass"))
    state.push(Scope(kind=ScopeKind.FUNCTION, name="outer_method"))
    state.push(Scope(kind=ScopeKind.CLASS, name="LocalClass"))
    state.push(Scope(kind=ScopeKind.FUNCTION, name="local_method"))

    # Check state
    assert state.in_class() is True
    assert state.in_function() is True
    assert state.get_containing_class() == "__module__.OuterClass.outer_method.LocalClass"
    assert len(state.stack) == 5


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
    result = generate_name_candidates(scope_stack, name)
    assert result == expected


def test_build_qualified_name_no_exclusions() -> None:
    """Test building qualified names without excluding any scopes."""
    scope_stack = (
        Scope(kind=ScopeKind.MODULE, name="__module__"),
        Scope(kind=ScopeKind.CLASS, name="Calculator"),
        Scope(kind=ScopeKind.FUNCTION, name="helper"),
    )
    result = build_qualified_name(scope_stack, "add")
    assert result == "__module__.Calculator.helper.add"


def test_build_qualified_name_exclude_functions() -> None:
    """Test building qualified names while excluding function scopes."""
    scope_stack = (
        Scope(kind=ScopeKind.MODULE, name="__module__"),
        Scope(kind=ScopeKind.CLASS, name="Calculator"),
        Scope(kind=ScopeKind.FUNCTION, name="helper"),
    )
    result = build_qualified_name(scope_stack, "add", exclude_kinds=frozenset({ScopeKind.FUNCTION}))
    assert result == "__module__.Calculator.add"


def test_build_qualified_name_exclude_classes() -> None:
    """Test building qualified names while excluding class scopes."""
    scope_stack = (
        Scope(kind=ScopeKind.MODULE, name="__module__"),
        Scope(kind=ScopeKind.CLASS, name="Calculator"),
        Scope(kind=ScopeKind.FUNCTION, name="compute"),
    )
    result = build_qualified_name(scope_stack, "helper", exclude_kinds=frozenset({ScopeKind.CLASS}))
    assert result == "__module__.compute.helper"


def test_find_first_match_found() -> None:
    """Test find_first_match when a match is found."""
    candidates = (
        "__module__.Outer.Inner.method",
        "__module__.Outer.method",
        "__module__.method",
    )
    registry = frozenset({"__module__.Outer.method", "__module__.other_func"})
    result = find_first_match(candidates, registry)
    assert result == "__module__.Outer.method"


def test_find_first_match_not_found() -> None:
    """Test find_first_match when no match is found."""
    candidates = ("__module__.unknown", "__module__.missing")
    registry = frozenset({"__module__.existing", "__module__.other"})
    result = find_first_match(candidates, registry)
    assert result is None


def test_find_first_match_empty_candidates() -> None:
    """Test find_first_match with empty candidates."""
    candidates = ()
    registry = frozenset({"__module__.func"})
    result = find_first_match(candidates, registry)
    assert result is None


def test_find_first_match_empty_registry() -> None:
    """Test find_first_match with empty registry."""
    candidates = ("__module__.func",)
    registry: frozenset[str] = frozenset()
    result = find_first_match(candidates, registry)
    assert result is None


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
