"""Unit tests for the scope_tracker module.

Tests cover the pure functions for scope stack management and name resolution
during AST traversal.
"""

import ast

import pytest

from annotation_prioritizer.models import QualifiedName, Scope, ScopeKind, make_qualified_name
from annotation_prioritizer.scope_tracker import (
    add_scope,
    build_qualified_name,
    create_initial_stack,
    drop_last_scope,
    extract_attribute_chain,
    find_first_match,
    generate_name_candidates,
    get_containing_class,
    get_current_scope,
    in_class,
    in_function,
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
    assert get_current_scope(stack) == class_scope

    # Push a function scope
    func_scope = Scope(kind=ScopeKind.FUNCTION, name="my_method")
    stack = add_scope(stack, func_scope)
    assert len(stack) == 3
    assert get_current_scope(stack) == func_scope

    # Pop function scope
    stack = drop_last_scope(stack)
    assert len(stack) == 2
    assert get_current_scope(stack) == class_scope

    # Pop class scope
    stack = drop_last_scope(stack)
    assert len(stack) == 1
    assert get_current_scope(stack) == Scope(kind=ScopeKind.MODULE, name="__module__")


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


def test_get_containing_class_no_class() -> None:
    """Test get_containing_class when not inside any class."""
    stack = create_initial_stack()
    # Just module scope
    assert get_containing_class(stack) is None

    # Module + function scope
    stack = add_scope(stack, Scope(kind=ScopeKind.FUNCTION, name="standalone_func"))
    assert get_containing_class(stack) is None


def test_get_containing_class_single_class() -> None:
    """Test get_containing_class with a single class in the stack."""
    stack = create_initial_stack()
    stack = add_scope(stack, Scope(kind=ScopeKind.CLASS, name="MyClass"))
    assert get_containing_class(stack) == "__module__.MyClass"

    # Add a function inside the class
    stack = add_scope(stack, Scope(kind=ScopeKind.FUNCTION, name="method"))
    assert get_containing_class(stack) == "__module__.MyClass"


def test_get_containing_class_nested_classes() -> None:
    """Test get_containing_class with nested classes."""
    stack = create_initial_stack()
    stack = add_scope(stack, Scope(kind=ScopeKind.CLASS, name="Outer"))
    assert get_containing_class(stack) == "__module__.Outer"

    stack = add_scope(stack, Scope(kind=ScopeKind.CLASS, name="Inner"))
    assert get_containing_class(stack) == "__module__.Outer.Inner"

    # Add a method in the inner class
    stack = add_scope(stack, Scope(kind=ScopeKind.FUNCTION, name="inner_method"))
    assert get_containing_class(stack) == "__module__.Outer.Inner"


def test_get_containing_class_function_then_class() -> None:
    """Test get_containing_class when class is defined inside a function."""
    stack = create_initial_stack()
    stack = add_scope(stack, Scope(kind=ScopeKind.FUNCTION, name="factory"))
    stack = add_scope(stack, Scope(kind=ScopeKind.CLASS, name="LocalClass"))
    assert get_containing_class(stack) == "__module__.factory.LocalClass"


def test_in_class() -> None:
    """Test in_class function for checking if inside a class."""
    stack = create_initial_stack()
    # Initially not in class
    assert in_class(stack) is False

    # Add a class
    stack = add_scope(stack, Scope(kind=ScopeKind.CLASS, name="MyClass"))
    assert in_class(stack) is True

    # Add a function inside the class
    stack = add_scope(stack, Scope(kind=ScopeKind.FUNCTION, name="method"))
    assert in_class(stack) is True

    # Pop the function, still in class
    stack = drop_last_scope(stack)
    assert in_class(stack) is True

    # Pop the class, no longer in class
    stack = drop_last_scope(stack)
    assert in_class(stack) is False


def test_in_function() -> None:
    """Test in_function function for checking if inside a function."""
    stack = create_initial_stack()
    # Initially not in function
    assert in_function(stack) is False

    # Add a function
    stack = add_scope(stack, Scope(kind=ScopeKind.FUNCTION, name="my_func"))
    assert in_function(stack) is True

    # Add a class inside the function
    stack = add_scope(stack, Scope(kind=ScopeKind.CLASS, name="LocalClass"))
    assert in_function(stack) is True

    # Pop the class, still in function
    stack = drop_last_scope(stack)
    assert in_function(stack) is True

    # Pop the function, no longer in function
    stack = drop_last_scope(stack)
    assert in_function(stack) is False


def test_complex_nesting() -> None:
    """Test complex nesting scenarios with all scope types."""
    stack = create_initial_stack()

    # Build: module -> class -> function -> class -> function
    stack = add_scope(stack, Scope(kind=ScopeKind.CLASS, name="OuterClass"))
    stack = add_scope(stack, Scope(kind=ScopeKind.FUNCTION, name="outer_method"))
    stack = add_scope(stack, Scope(kind=ScopeKind.CLASS, name="LocalClass"))
    stack = add_scope(stack, Scope(kind=ScopeKind.FUNCTION, name="local_method"))

    # Check state
    assert in_class(stack) is True
    assert in_function(stack) is True
    assert get_containing_class(stack) == "__module__.OuterClass.outer_method.LocalClass"
    assert len(stack) == 5


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
        make_qualified_name("__module__.Outer.Inner.method"),
        make_qualified_name("__module__.Outer.method"),
        make_qualified_name("__module__.method"),
    )
    registry = frozenset(
        {
            make_qualified_name("__module__.Outer.method"),
            make_qualified_name("__module__.other_func"),
        }
    )
    result = find_first_match(candidates, registry)
    assert result == make_qualified_name("__module__.Outer.method")


def test_find_first_match_not_found() -> None:
    """Test find_first_match when no match is found."""
    candidates = (make_qualified_name("__module__.unknown"), make_qualified_name("__module__.missing"))
    registry = frozenset(
        {
            make_qualified_name("__module__.existing"),
            make_qualified_name("__module__.other"),
        }
    )
    result = find_first_match(candidates, registry)
    assert result is None


def test_find_first_match_empty_candidates() -> None:
    """Test find_first_match with empty candidates."""
    candidates = ()
    registry = frozenset({make_qualified_name("__module__.func")})
    result = find_first_match(candidates, registry)
    assert result is None


def test_find_first_match_empty_registry() -> None:
    """Test find_first_match with empty registry."""
    candidates = (make_qualified_name("__module__.func"),)
    registry: frozenset[QualifiedName] = frozenset()
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
