# pyright: reportPrivateUsage=false
"""Unit tests for call counting functionality."""

import ast
from pathlib import Path
from unittest.mock import patch

import pytest

from annotation_prioritizer.ast_visitors.call_counter import (
    CallCountVisitor,
    UnresolvableCall,
)
from annotation_prioritizer.iteration import first
from annotation_prioritizer.models import make_qualified_name
from tests.helpers.factories import make_function_info, make_parameter
from tests.helpers.function_parsing import build_position_index_from_source


def _get_first_call_node(code: str) -> ast.Call:
    """Extract the first Call node from parsed code."""
    tree = ast.parse(code)
    return next(node for node in ast.walk(tree) if isinstance(node, ast.Call))


def _create_visitor_and_visit_call(
    code: str, call_node: ast.Call
) -> tuple[CallCountVisitor, tuple[UnresolvableCall, ...]]:
    """Create a visitor and visit a call node, returning visitor and unresolvable calls."""
    _, position_index, known_classes = build_position_index_from_source(code)
    visitor = CallCountVisitor((), position_index, known_classes, code)
    visitor.visit_Call(call_node)
    return visitor, visitor.get_unresolvable_calls()


def test_self_call_outside_class_context() -> None:
    """Test self.method() calls that occur outside class context."""
    # Parse code that contains self.method() outside of a class
    # This tests the edge case where self appears at module level
    edge_case_code = """
# Module-level function that has a self.method() call
# This would be invalid in real Python but tests our handling
def method():
    pass

# Simulate a call that looks like self.method() outside class context
# We'll extract this call node from the parsed AST
self.method()
"""

    # Parse the code to get real AST nodes
    tree, position_index, known_classes = build_position_index_from_source(edge_case_code)

    # Find the self.method() call node in the AST
    def is_self_method_call(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "self"
            and node.func.attr == "method"
        )

    call_node = first(ast.walk(tree), is_self_method_call)
    assert call_node is not None, "Could not find self.method() call in parsed AST"
    assert isinstance(call_node, ast.Call)

    # Create a visitor with the known function
    known_functions = (
        make_function_info(
            "method",
            line_number=1,
            file_path=Path("dummy.py"),
        ),
    )

    visitor = CallCountVisitor(known_functions, position_index, known_classes, edge_case_code)

    # Test by visiting the call - self.method() outside a class should not resolve
    visitor.visit_Call(call_node)
    assert visitor.call_counts[make_qualified_name("__module__.method")] == 0  # Should not resolve


def test_complex_qualified_calls() -> None:
    """Test complex qualified calls - unresolved compound names should not be counted."""
    # Parse code containing complex qualified calls like outer.inner.method()
    complex_call_code = """
def method():
    pass

# Complex qualified call that can't be resolved
# This tests handling of compound attribute access
outer.inner.method()
"""

    # Parse the code to get real AST nodes
    tree, position_index, known_classes = build_position_index_from_source(complex_call_code)

    # Find the outer.inner.method() call node in the AST
    def is_outer_inner_method_call(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "method"
            and isinstance(node.func.value, ast.Attribute)
            and node.func.value.attr == "inner"
            and isinstance(node.func.value.value, ast.Name)
            and node.func.value.value.id == "outer"
        )

    call_node = first(ast.walk(tree), is_outer_inner_method_call)
    assert call_node is not None, "Could not find outer.inner.method() call in parsed AST"
    assert isinstance(call_node, ast.Call)

    # Create a visitor with the known function
    known_functions = (
        make_function_info(
            "method",
            line_number=1,
            file_path=Path("dummy.py"),
        ),
    )

    visitor = CallCountVisitor(known_functions, position_index, known_classes, complex_call_code)

    # Test by visiting the call - unresolved references should not be counted
    visitor.visit_Call(call_node)
    # Unresolved compound name not counted
    assert visitor.call_counts[make_qualified_name("__module__.method")] == 0


def test_extract_call_with_dynamic_call() -> None:
    """Test that dynamic calls return None."""
    # Parse code containing a dynamic call: getattr(obj, 'method')()
    dynamic_call_code = """
# Dynamic function call that can't be resolved statically
obj = object()
getattr(obj, 'method')()
"""

    # Parse the code to get real AST nodes
    tree, position_index, known_classes = build_position_index_from_source(dynamic_call_code)

    # Find the getattr(obj, 'method')() call node in the AST
    def is_getattr_dynamic_call(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Call)
            and isinstance(node.func.func, ast.Name)
            and node.func.func.id == "getattr"
        )

    call_node = first(ast.walk(tree), is_getattr_dynamic_call)
    assert call_node is not None, "Could not find getattr() dynamic call in parsed AST"
    assert isinstance(call_node, ast.Call)

    # Create a visitor with the new signature
    visitor = CallCountVisitor((), position_index, known_classes, dynamic_call_code)

    # Test that resolve_call_name returns None for dynamic calls
    result = visitor._resolve_call_name(call_node)
    assert result is None


def test_compound_class_detection() -> None:
    """Test that nested classes are detected and tracked in known_classes."""
    source = """
class Outer:
    class Inner:
        class Nested:
            pass
"""
    _, _, known_classes = build_position_index_from_source(source)

    assert "__module__.Outer" in known_classes
    assert "__module__.Outer.Inner" in known_classes
    assert "__module__.Outer.Inner.Nested" in known_classes


def test_resolve_compound_class_in_function_scope() -> None:
    """Test compound class resolution for classes defined in functions."""
    source = """
def my_function():
    class Outer:
        class Inner:
            def method(self):
                pass

    # This compound call should be resolved
    Outer.Inner.method()
"""
    tree, position_index, known_classes = build_position_index_from_source(source)

    # Create a visitor with the Inner.method as a known function
    known_functions = (
        make_function_info(
            "method",
            qualified_name=make_qualified_name("__module__.my_function.Outer.Inner.method"),
            line_number=5,
            file_path=Path("test.py"),
        ),
    )

    visitor = CallCountVisitor(known_functions, position_index, known_classes, source)
    visitor.visit(tree)

    # The Outer.Inner.method() call is counted because position-aware resolution
    # correctly resolves compound class references within the same function scope
    assert visitor.call_counts[make_qualified_name("__module__.my_function.Outer.Inner.method")] == 1


def test_compound_reference_through_function_not_resolved() -> None:
    """Test that compound references through functions are not resolved."""
    code = """
def my_function():
    pass

def test():
    # Attempt to access an attribute through a function (invalid)
    my_function.Inner.method()
"""

    tree, position_index, known_classes = build_position_index_from_source(code)

    known_functions = (
        make_function_info(
            "my_function",
            qualified_name=make_qualified_name("__module__.my_function"),
            line_number=2,
            file_path=Path("test.py"),
        ),
    )

    visitor = CallCountVisitor(known_functions, position_index, known_classes, code)
    visitor.visit(tree)

    # The call should not be resolved since my_function is a FUNCTION, not a CLASS
    # my_function itself is in call_counts with 0 (it's a known function)
    assert visitor.call_counts[make_qualified_name("__module__.my_function")] == 0
    # The compound call my_function.Inner.method() should be unresolvable
    unresolvable = visitor.get_unresolvable_calls()
    assert len(unresolvable) == 1
    assert "my_function.Inner.method()" in unresolvable[0].call_text


def test_unresolvable_call_text_truncation() -> None:
    """Test that very long unresolvable calls are truncated to 200 chars + ellipsis."""
    # Create a call with more than 200 characters
    long_args = ", ".join([f"arg{i}" for i in range(100)])
    long_call_code = f"""
# This unresolvable call has more than 200 characters
unknown_function({long_args})
"""

    call_node = _get_first_call_node(long_call_code)
    _, unresolvable_calls = _create_visitor_and_visit_call(long_call_code, call_node)

    assert len(unresolvable_calls) == 1
    assert unresolvable_calls[0].call_text.endswith("...")
    assert len(unresolvable_calls[0].call_text) == 203  # 200 chars + "..."


@pytest.mark.parametrize("return_value", [None, ""])
def test_unresolvable_call_when_source_segment_fails(return_value: str | None) -> None:
    """Test handling when ast.get_source_segment returns None or empty string."""
    simple_code = "unknown_func()"
    call_node = _get_first_call_node(simple_code)

    _, position_index, known_classes = build_position_index_from_source(simple_code)
    visitor = CallCountVisitor((), position_index, known_classes, simple_code)

    with patch.object(ast, "get_source_segment", return_value=return_value):
        visitor.visit_Call(call_node)
        unresolvable_calls = visitor.get_unresolvable_calls()

        assert len(unresolvable_calls) == 1
        assert unresolvable_calls[0].call_text == "<unable to extract call text>"


def test_compound_class_reference_through_instantiated_variable() -> None:
    """Test compound class references using a variable holding an instance.

    When a variable holds an instance of a class, compound attribute access
    through that variable should resolve the nested class method calls.
    """
    code = """
class Outer:
    class Inner:
        def method(self):
            return 1

def test():
    # Create an instance and access nested class through it
    obj = Outer()
    # Access Inner through the instance's class
    obj.Inner.method()
"""

    tree, position_index, known_classes = build_position_index_from_source(code)

    known_functions = (
        make_function_info(
            "method",
            qualified_name=make_qualified_name("__module__.Outer.Inner.method"),
            parameters=(make_parameter("self"),),
            line_number=4,
            file_path=Path("test.py"),
        ),
    )

    visitor = CallCountVisitor(known_functions, position_index, known_classes, code)
    visitor.visit(tree)

    # obj.Inner.method() should resolve through compound reference resolution
    # obj has target_class=__module__.Outer, so obj.Inner should resolve to __module__.Outer.Inner
    assert visitor.call_counts[make_qualified_name("__module__.Outer.Inner.method")] == 1
