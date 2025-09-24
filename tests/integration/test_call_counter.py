# pyright: reportPrivateUsage=false
"""Tests for call counting functionality."""

import ast
from unittest.mock import patch

import pytest

from annotation_prioritizer.ast_visitors.call_counter import (
    CallCountVisitor,
    UnresolvableCall,
)
from annotation_prioritizer.ast_visitors.class_discovery import build_class_registry
from annotation_prioritizer.ast_visitors.variable_discovery import build_variable_registry
from annotation_prioritizer.iteration import first
from annotation_prioritizer.models import Scope, ScopeKind, make_qualified_name
from annotation_prioritizer.scope_tracker import add_scope, drop_last_scope
from tests.helpers.factories import make_function_info, make_parameter
from tests.helpers.function_parsing import count_calls_from_file, parse_functions_from_file
from tests.helpers.temp_files import temp_python_file


def test_count_function_calls_simple_functions() -> None:
    """Test counting calls to simple module-level functions."""
    code = """
def func_a():
    return 1

def func_b():
    return 2

def caller():
    func_a()
    func_a()
    func_b()
    return func_a() + func_b()
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            make_function_info(
                "func_a",
                line_number=2,
                file_path=temp_path,
            ),
            make_function_info(
                "func_b",
                line_number=5,
                file_path=temp_path,
            ),
            make_function_info(
                "caller",
                line_number=8,
                file_path=temp_path,
            ),
        )

        result, _ = count_calls_from_file(temp_path, known_functions)

        # Convert to dict for easier testing
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        assert call_counts[make_qualified_name("__module__.func_a")] == 3  # Called 3 times
        assert call_counts[make_qualified_name("__module__.func_b")] == 2  # Called 2 times
        assert call_counts[make_qualified_name("__module__.caller")] == 0  # Not called


def test_count_method_calls() -> None:
    """Test counting calls to class methods."""
    code = """
class Calculator:
    def add(self, a, b):
        return a + b

    def multiply(self, a, b):
        return a * b

    def calculate(self):
        result1 = self.add(1, 2)
        result2 = self.multiply(3, 4)
        return self.add(result1, result2)

def use_calculator():
    calc = Calculator()
    return calc.add(5, 6)
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            make_function_info(
                "add",
                qualified_name=make_qualified_name("__module__.Calculator.add"),
                parameters=(
                    make_parameter("self"),
                    make_parameter("a"),
                    make_parameter("b"),
                ),
                line_number=3,
                file_path=temp_path,
            ),
            make_function_info(
                "multiply",
                qualified_name=make_qualified_name("__module__.Calculator.multiply"),
                parameters=(
                    make_parameter("self"),
                    make_parameter("a"),
                    make_parameter("b"),
                ),
                line_number=6,
                file_path=temp_path,
            ),
        )

        result, _ = count_calls_from_file(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # self.add() called twice in calculate method = 2 times
        # calc.add() in use_calculator resolves to Calculator.add() = 1 time
        # Total: 3 times
        assert call_counts[make_qualified_name("__module__.Calculator.add")] == 3
        assert call_counts[make_qualified_name("__module__.Calculator.multiply")] == 1


def test_count_static_method_calls() -> None:
    """Test counting calls to static methods via class name."""
    code = """
class Utils:
    @staticmethod
    def format_number(n):
        return f"#{n}"

    def use_static(self):
        return Utils.format_number(42)

def external_use():
    return Utils.format_number(100)
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            make_function_info(
                "format_number",
                qualified_name=make_qualified_name("__module__.Utils.format_number"),
                parameters=(make_parameter("n"),),
                line_number=4,
                file_path=temp_path,
            ),
        )

        result, _ = count_calls_from_file(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # Utils.format_number() called twice
        assert call_counts[make_qualified_name("__module__.Utils.format_number")] == 2


def test_count_no_calls() -> None:
    """Test with functions that are never called."""
    code = """
def unused_function():
    pass

def another_unused():
    pass
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            make_function_info(
                "unused_function",
                line_number=2,
                file_path=temp_path,
            ),
            make_function_info(
                "another_unused",
                line_number=5,
                file_path=temp_path,
            ),
        )

        result, _ = count_calls_from_file(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        assert call_counts[make_qualified_name("__module__.unused_function")] == 0
        assert call_counts[make_qualified_name("__module__.another_unused")] == 0


def test_count_unknown_functions_ignored() -> None:
    """Test that calls to unknown functions are ignored."""
    code = """
def known_func():
    pass

def caller():
    known_func()
    unknown_func()  # This should be ignored
    imported_func()  # This should also be ignored
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            make_function_info(
                "known_func",
                line_number=2,
                file_path=temp_path,
            ),
        )

        result, _ = count_calls_from_file(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        assert call_counts[make_qualified_name("__module__.known_func")] == 1


def test_count_calls_nonexistent_file() -> None:
    """Test handling of nonexistent files."""
    result, _ = count_calls_from_file("/nonexistent/file.py", ())
    assert result == ()


def test_count_calls_syntax_error() -> None:
    """Test handling of files with syntax errors."""
    code = """
def broken_syntax(
    # Missing closing parenthesis
"""

    with temp_python_file(code) as temp_path:
        result, _ = count_calls_from_file(temp_path, ())
        assert result == ()


def test_count_calls_empty_known_functions() -> None:
    """Test with empty known functions list."""
    code = """
def some_function():
    pass
"""

    with temp_python_file(code) as temp_path:
        result, _ = count_calls_from_file(temp_path, ())
        assert result == ()


def test_count_nested_class_methods() -> None:
    """Test counting calls to methods in nested classes."""
    code = """
class Outer:
    class Inner:
        def inner_method(self):
            return 1

    def outer_method(self):
        inner = self.Inner()
        return inner.inner_method()  # This won't be tracked as same-module call

    def use_inner_directly(self):
        # This also won't be tracked as it's not self.inner_method
        return Outer.Inner().inner_method()
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            make_function_info(
                "inner_method",
                qualified_name=make_qualified_name("__module__.Outer.Inner.inner_method"),
                parameters=(make_parameter("self"),),
                line_number=4,
                file_path=temp_path,
            ),
        )

        result, _ = count_calls_from_file(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # Due to our simple implementation, these complex calls won't be tracked
        assert call_counts[make_qualified_name("__module__.Outer.Inner.inner_method")] == 0


def test_count_edge_case_calls() -> None:
    """Test edge cases in call name extraction."""
    code = """
class MyClass:
    def method_in_class(self):
        return 1

def module_function():
    # This creates a self.method() call but without class context
    obj = MyClass()
    # This should trigger the func.attr path (line 81) for complex qualified calls
    return obj.method_in_class()

# Module level call without class context to cover line 70
def standalone_method():
    pass

def test_self_without_class():
    # This would be invalid Python but we should handle it gracefully
    # This is just to test the code path where self.method() occurs outside class
    pass
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            make_function_info(
                "method_in_class",
                qualified_name=make_qualified_name("__module__.MyClass.method_in_class"),
                parameters=(make_parameter("self"),),
                line_number=3,
                file_path=temp_path,
            ),
            make_function_info(
                "standalone_method",
                line_number=12,
                file_path=temp_path,
            ),
        )

        result, _ = count_calls_from_file(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # The obj.method_in_class() call resolves to MyClass.method_in_class through variable tracking
        assert call_counts[make_qualified_name("__module__.MyClass.method_in_class")] == 1
        assert call_counts[make_qualified_name("__module__.standalone_method")] == 0


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
    tree = ast.parse(edge_case_code)

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
            file_path="dummy.py",
        ),
    )

    class_registry = build_class_registry(ast.parse(""))
    variable_registry = build_variable_registry(ast.parse(edge_case_code), class_registry)
    visitor = CallCountVisitor(known_functions, class_registry, edge_case_code, variable_registry)

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
    tree = ast.parse(complex_call_code)

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
            file_path="dummy.py",
        ),
    )

    class_registry = build_class_registry(ast.parse(""))
    variable_registry = build_variable_registry(ast.parse(complex_call_code), class_registry)
    visitor = CallCountVisitor(known_functions, class_registry, complex_call_code, variable_registry)

    # Test by visiting the call - unresolved references should not be counted
    visitor.visit_Call(call_node)
    # Unresolved compound name not counted
    assert visitor.call_counts[make_qualified_name("__module__.method")] == 0


def test_function_calls_in_nested_functions() -> None:
    """Test counting calls made inside nested functions."""
    code = """
def outer_function():
    def inner_function():
        return outer_function()  # Call to outer function from inside inner

    def another_inner():
        return inner_function() + helper_function()  # Calls to other functions

    return inner_function() + another_inner()

def helper_function():
    return 42

def top_level_caller():
    return outer_function() + helper_function()
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            make_function_info(
                "outer_function",
                line_number=2,
                file_path=temp_path,
            ),
            make_function_info(
                "inner_function",
                qualified_name=make_qualified_name("__module__.outer_function.inner_function"),
                line_number=3,
                file_path=temp_path,
            ),
            make_function_info(
                "another_inner",
                qualified_name=make_qualified_name("__module__.outer_function.another_inner"),
                line_number=6,
                file_path=temp_path,
            ),
            make_function_info(
                "helper_function",
                line_number=11,
                file_path=temp_path,
            ),
        )

        result, _ = count_calls_from_file(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # outer_function() called:
        # - once from inner_function
        # - once from top_level_caller
        # Total: 2 calls
        assert call_counts[make_qualified_name("__module__.outer_function")] == 2

        # inner_function() called:
        # - once from another_inner
        # - once from outer_function itself
        # Total: 2 calls
        assert call_counts[make_qualified_name("__module__.outer_function.inner_function")] == 2

        # another_inner() called:
        # - once from outer_function
        # Total: 1 call
        assert call_counts[make_qualified_name("__module__.outer_function.another_inner")] == 1

        # helper_function() called:
        # - once from another_inner
        # - once from top_level_caller
        # Total: 2 calls
        assert call_counts[make_qualified_name("__module__.helper_function")] == 2


def test_method_calls_in_nested_functions() -> None:
    """Test counting method calls inside nested functions within classes."""
    code = """
class Calculator:
    def complex_operation(self):
        def inner_helper():
            return self.add(1, 2)  # Method call from nested function

        def another_helper():
            base = self.multiply(3, 4)  # Another method call from nested function
            return base + inner_helper()

        return another_helper() + self.add(5, 6)  # Direct method call

    def add(self, a, b):
        return a + b

    def multiply(self, a, b):
        return a * b
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            make_function_info(
                "add",
                qualified_name=make_qualified_name("__module__.Calculator.add"),
                parameters=(
                    make_parameter("self"),
                    make_parameter("a"),
                    make_parameter("b"),
                ),
                line_number=14,
                file_path=temp_path,
            ),
            make_function_info(
                "multiply",
                qualified_name=make_qualified_name("__module__.Calculator.multiply"),
                parameters=(
                    make_parameter("self"),
                    make_parameter("a"),
                    make_parameter("b"),
                ),
                line_number=17,
                file_path=temp_path,
            ),
        )

        result, _ = count_calls_from_file(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # self.add() called:
        # - once from inner_helper nested function
        # - once from complex_operation directly
        # Total: 2 calls
        assert call_counts[make_qualified_name("__module__.Calculator.add")] == 2

        # self.multiply() called:
        # - once from another_helper nested function
        # Total: 1 call
        assert call_counts[make_qualified_name("__module__.Calculator.multiply")] == 1


def test_deeply_nested_function_calls() -> None:
    """Test function calls in deeply nested structures."""
    code = """
class OuterClass:
    def outer_method(self):
        def level1_function():
            def level2_function():
                def level3_function():
                    return self.helper_method()  # Deep nested method call
                return level3_function() + module_function()  # Call to module function
            return level2_function()
        return level1_function()

    def helper_method(self):
        return 42

def module_function():
    return 100
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            make_function_info(
                "helper_method",
                qualified_name=make_qualified_name("__module__.OuterClass.helper_method"),
                parameters=(make_parameter("self"),),
                line_number=10,
                file_path=temp_path,
            ),
            make_function_info(
                "module_function",
                line_number=13,
                file_path=temp_path,
            ),
        )

        result, _ = count_calls_from_file(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # self.helper_method() called once from level3_function
        assert call_counts[make_qualified_name("__module__.OuterClass.helper_method")] == 1

        # module_function() called once from level2_function
        assert call_counts[make_qualified_name("__module__.module_function")] == 1


def test_nested_class_with_function_calls() -> None:
    """Test function calls inside methods of nested classes."""
    code = """
class Outer:
    class Inner:
        def inner_method(self):
            def nested_function():
                return module_helper()  # Call to module function from nested function
            return nested_function() + self.other_inner_method()

        def other_inner_method(self):
            return 10

def module_helper():
    return 5
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            make_function_info(
                "other_inner_method",
                qualified_name=make_qualified_name("__module__.Outer.Inner.other_inner_method"),
                parameters=(make_parameter("self"),),
                line_number=8,
                file_path=temp_path,
            ),
            make_function_info(
                "module_helper",
                line_number=11,
                file_path=temp_path,
            ),
        )

        result, _ = count_calls_from_file(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # self.other_inner_method() called once from inner_method
        assert call_counts[make_qualified_name("__module__.Outer.Inner.other_inner_method")] == 1

        # module_helper() called once from nested_function
        assert call_counts[make_qualified_name("__module__.module_helper")] == 1


def test_extract_call_with_dynamic_call() -> None:
    """Test that dynamic calls return None."""
    # Parse code containing a dynamic call: getattr(obj, 'method')()
    dynamic_call_code = """
# Dynamic function call that can't be resolved statically
obj = object()
getattr(obj, 'method')()
"""

    # Parse the code to get real AST nodes
    tree = ast.parse(dynamic_call_code)

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

    # Create a visitor with an empty class registry
    class_registry = build_class_registry(ast.parse(""))
    variable_registry = build_variable_registry(ast.parse(dynamic_call_code), class_registry)
    visitor = CallCountVisitor((), class_registry, dynamic_call_code, variable_registry)

    # Test that resolve_call_name returns None for dynamic calls
    result = visitor._resolve_call_name(call_node)
    assert result is None


def test_resolve_compound_class_not_in_registry() -> None:
    """Test compound class resolution when class not in registry."""
    source = """
class Outer:
    class Inner:
        class Nested:
            pass
"""
    tree = ast.parse(source)
    class_registry = build_class_registry(tree)

    variable_registry = build_variable_registry(tree, class_registry)
    visitor = CallCountVisitor((), class_registry, source, variable_registry)

    # Try to resolve a compound name that doesn't exist
    result = visitor._resolve_class_name("NonExistent.Inner")
    assert result is None

    # Try within a class scope - test the successful case
    visitor._scope_stack = add_scope(visitor._scope_stack, Scope(kind=ScopeKind.CLASS, name="Outer"))
    # This should match since __module__.Outer.Inner.Nested exists
    result = visitor._resolve_class_name("Inner.Nested")
    assert result == "__module__.Outer.Inner.Nested"
    visitor._scope_stack = drop_last_scope(visitor._scope_stack)

    # Try within a class scope (simulate being inside a different class)
    visitor._scope_stack = add_scope(visitor._scope_stack, Scope(kind=ScopeKind.CLASS, name="SomeClass"))
    result = visitor._resolve_class_name("Another.Nested")
    assert result is None
    visitor._scope_stack = drop_last_scope(visitor._scope_stack)

    # Also test when scope is a function (not a class)
    visitor._scope_stack = add_scope(visitor._scope_stack, Scope(kind=ScopeKind.FUNCTION, name="some_func"))
    result = visitor._resolve_class_name("Foo.Bar")
    assert result is None


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
    tree = ast.parse(source)
    class_registry = build_class_registry(tree)

    # Create a visitor with the Inner.method as a known function
    known_functions = (
        make_function_info(
            "method",
            qualified_name=make_qualified_name("__module__.my_function.Outer.Inner.method"),
            line_number=5,
            file_path="test.py",
        ),
    )

    variable_registry = build_variable_registry(tree, class_registry)
    visitor = CallCountVisitor(known_functions, class_registry, source, variable_registry)
    visitor.visit(tree)

    assert visitor.call_counts[make_qualified_name("__module__.my_function.Outer.Inner.method")] == 1


def test_async_function_calls() -> None:
    """Test counting calls to and from async functions."""
    code = """
async def async_outer():
    async def async_inner():
        return await async_outer()  # Call to outer async function

    def sync_inner():
        return regular_helper()  # Call to regular function from sync inner

    result = await async_inner()
    return result + sync_inner()

def regular_helper():
    return 10

async def top_level_async():
    return await async_outer() + regular_helper()
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            make_function_info(
                "async_outer",
                line_number=2,
                file_path=temp_path,
            ),
            make_function_info(
                "async_inner",
                qualified_name=make_qualified_name("__module__.async_outer.async_inner"),
                line_number=3,
                file_path=temp_path,
            ),
            make_function_info(
                "regular_helper",
                line_number=12,
                file_path=temp_path,
            ),
        )

        result, _ = count_calls_from_file(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # async_outer() called:
        # - once from async_inner (await async_outer())
        # - once from top_level_async (await async_outer())
        # Total: 2 calls
        assert call_counts[make_qualified_name("__module__.async_outer")] == 2

        # async_inner() called:
        # - once from async_outer (await async_inner())
        # Total: 1 call
        assert call_counts[make_qualified_name("__module__.async_outer.async_inner")] == 1

        # regular_helper() called:
        # - once from sync_inner nested function
        # - once from top_level_async
        # Total: 2 calls
        assert call_counts[make_qualified_name("__module__.regular_helper")] == 2


def test_builtin_shadowing() -> None:
    """Test that user-defined classes with builtin names are resolved correctly."""
    code = """
class list:  # User-defined class with builtin name
    @staticmethod
    def append(item):
        pass

def test():
    list.append("x")  # Should resolve to user-defined list class
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            make_function_info(
                "append",
                qualified_name=make_qualified_name("__module__.list.append"),  # User-defined class method
                parameters=(make_parameter("item"),),
                line_number=4,
                file_path=temp_path,
            ),
            make_function_info(
                "append",
                qualified_name=make_qualified_name("list.append"),  # Never resolved (no builtin tracking)
                parameters=(
                    make_parameter("self"),
                    make_parameter("item"),
                ),
                line_number=1,
                file_path=temp_path,
            ),
        )

        result, _ = count_calls_from_file(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # User-defined class method should be called
        # The "list.append" entry (without __module__) is never resolved since we don't track builtins
        assert call_counts[make_qualified_name("__module__.list.append")] == 1
        assert call_counts[make_qualified_name("list.append")] == 0


def test_complex_expression_calls_handled_gracefully() -> None:
    """Test that complex expressions in method calls don't crash."""
    code = """
class MyClass:
    def method(self):
        pass

def test():
    # Complex expressions that can't be resolved
    get_obj()[0].method()  # Should not crash
    (a + b).method()       # Should not crash
    foo().bar.method()     # Should not crash
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            make_function_info(
                "method",
                qualified_name=make_qualified_name("__module__.MyClass.method"),
                parameters=(make_parameter("self"),),
                line_number=3,
                file_path=temp_path,
            ),
        )

        # Should not crash, just return 0 calls since we can't resolve complex expressions
        result, _ = count_calls_from_file(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        assert call_counts[make_qualified_name("__module__.MyClass.method")] == 0


def test_unresolvable_class_references_not_counted() -> None:
    """Test that unresolvable class references are consistently not counted."""
    code = """
class KnownClass:
    def method(self):
        pass

def test():
    # These should not be counted as they can't be resolved
    UnknownClass.method()      # Unknown class
    unknown_var.method()       # Variable (not a class)
    Outer.Unknown.method()     # Partially unknown compound name
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            make_function_info(
                "method",
                qualified_name=make_qualified_name("__module__.KnownClass.method"),
                parameters=(make_parameter("self"),),
                line_number=3,
                file_path=temp_path,
            ),
        )

        result, _ = count_calls_from_file(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # None of the unresolvable references should be counted
        assert call_counts[make_qualified_name("__module__.KnownClass.method")] == 0


def test_builtin_functions_not_reported_as_unresolvable() -> None:
    """Test that built-in function calls are not reported as unresolvable."""
    code = """
def process_data(data):
    # Built-in functions - should NOT be unresolvable
    print("Processing...")
    length = len(data)
    total = sum(data)
    sorted_data = sorted(data)
    max_val = max(data)
    min_val = min(data)

    # User-defined function call
    result = custom_function(data)

    # Method call on unknown object - should be unresolvable
    unknown_obj.method()

    return result

def custom_function(x):
    return x * 2
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            make_function_info(
                "process_data",
                qualified_name=make_qualified_name("__module__.process_data"),
                parameters=(make_parameter("data"),),
                line_number=1,
                file_path=temp_path,
            ),
            make_function_info(
                "custom_function",
                qualified_name=make_qualified_name("__module__.custom_function"),
                parameters=(make_parameter("x"),),
                line_number=18,
                file_path=temp_path,
            ),
        )

        result, unresolvable_calls = count_calls_from_file(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # custom_function should be counted
        assert call_counts[make_qualified_name("__module__.custom_function")] == 1

        # Only unknown_obj.method() should be unresolvable
        # Built-in functions (print, len, sum, sorted, max, min) should NOT be unresolvable
        assert len(unresolvable_calls) == 1
        assert "unknown_obj.method()" in unresolvable_calls[0].call_text


def test_classmethod_cls_calls() -> None:
    """Test that cls.method() calls in @classmethod are properly counted."""
    source = """
class Calculator:
    @classmethod
    def create_and_compute(cls, x, y):
        # cls.add should be resolved and counted
        result = cls.add(x, y)
        # cls.multiply should be resolved and counted
        product = cls.multiply(x, y)
        return result, product

    @classmethod
    def add(cls, a, b):
        return a + b

    @classmethod
    def multiply(cls, a, b):
        return a * b

    @classmethod
    def complex_operation(cls):
        # Nested function using cls
        def helper():
            return cls.add(1, 2)  # Should resolve to Calculator.add

        # Direct cls call
        base = cls.multiply(3, 4)  # Should resolve to Calculator.multiply
        return base + helper()

# Usage outside class
Calculator.create_and_compute(5, 10)
"""

    with temp_python_file(source) as temp_path:
        # Parse to get function info
        functions = parse_functions_from_file(temp_path)

        # Count calls
        result, _ = count_calls_from_file(temp_path, functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # cls.add() should be counted:
        # - once in create_and_compute
        # - once in complex_operation's helper function
        assert call_counts.get(make_qualified_name("__module__.Calculator.add"), 0) == 2, (
            f"Expected 2 calls to Calculator.add, got "
            f"{call_counts.get(make_qualified_name('__module__.Calculator.add'), 0)}"
        )

        # cls.multiply() should be counted:
        # - once in create_and_compute
        # - once in complex_operation directly
        multiply_count = call_counts.get(make_qualified_name("__module__.Calculator.multiply"), 0)
        assert multiply_count == 2, f"Expected 2 calls to Calculator.multiply, got {multiply_count}"


def _get_first_call_node(code: str) -> ast.Call:
    """Extract the first Call node from parsed code."""
    tree = ast.parse(code)
    return next(node for node in ast.walk(tree) if isinstance(node, ast.Call))


def _create_visitor_and_visit_call(
    code: str, call_node: ast.Call
) -> tuple[CallCountVisitor, tuple[UnresolvableCall, ...]]:
    """Create a visitor and visit a call node, returning visitor and unresolvable calls."""
    tree = ast.parse(code)
    class_registry = build_class_registry(tree)
    variable_registry = build_variable_registry(tree, class_registry)
    visitor = CallCountVisitor((), class_registry, code, variable_registry)
    visitor.visit_Call(call_node)
    return visitor, visitor.get_unresolvable_calls()


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

    tree = ast.parse(simple_code)
    class_registry = build_class_registry(tree)
    variable_registry = build_variable_registry(tree, class_registry)
    visitor = CallCountVisitor((), class_registry, simple_code, variable_registry)

    with patch.object(ast, "get_source_segment", return_value=return_value):
        visitor.visit_Call(call_node)
        unresolvable_calls = visitor.get_unresolvable_calls()

        assert len(unresolvable_calls) == 1
        assert unresolvable_calls[0].call_text == "<unable to extract call text>"


def test_count_instance_method_calls_via_variables() -> None:
    """Test that instance method calls through variables are counted."""
    code = """
class Calculator:
    def add(self, a, b):
        return a + b

def use_calculator():
    calc = Calculator()
    return calc.add(5, 6)  # Should be counted
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            make_function_info(
                "add",
                qualified_name=make_qualified_name("__module__.Calculator.add"),
                parameters=(
                    make_parameter("self"),
                    make_parameter("a"),
                    make_parameter("b"),
                ),
                line_number=3,
                file_path=temp_path,
            ),
        )

        result, _ = count_calls_from_file(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # calc.add() should be counted once
        assert call_counts[make_qualified_name("__module__.Calculator.add")] == 1


def test_variable_reassignment_uses_final_type() -> None:
    """Test that reassigned variables use their final type for all calls.

    Note: This is a limitation of the two-stage approach - the variable registry
    only tracks the final assignment, so all calls use that type.
    """
    code = """
class Calculator:
    def add(self, a, b):
        return a + b

class Helper:
    def add(self, x, y):
        return x + y

def test():
    obj = Calculator()
    obj.add(1, 2)  # Registry will have obj as Helper (final type)
    obj = Helper()
    obj.add(3, 4)  # Registry will have obj as Helper (final type)
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            make_function_info(
                "add",
                qualified_name=make_qualified_name("__module__.Calculator.add"),
                parameters=(
                    make_parameter("self"),
                    make_parameter("a"),
                    make_parameter("b"),
                ),
                line_number=3,
                file_path=temp_path,
            ),
            make_function_info(
                "add",
                qualified_name=make_qualified_name("__module__.Helper.add"),
                parameters=(
                    make_parameter("self"),
                    make_parameter("x"),
                    make_parameter("y"),
                ),
                line_number=7,
                file_path=temp_path,
            ),
        )

        result, _ = count_calls_from_file(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # Both obj.add() calls resolve to Helper.add (final type in registry)
        assert call_counts[make_qualified_name("__module__.Calculator.add")] == 0
        assert call_counts[make_qualified_name("__module__.Helper.add")] == 2


def test_parameter_type_annotations_enable_resolution() -> None:
    """Test that parameter type annotations enable method resolution."""
    code = """
class Calculator:
    def add(self, a, b):
        return a + b

def process(calc: Calculator):
    return calc.add(10, 20)
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            make_function_info(
                "add",
                qualified_name=make_qualified_name("__module__.Calculator.add"),
                parameters=(
                    make_parameter("self"),
                    make_parameter("a"),
                    make_parameter("b"),
                ),
                line_number=3,
                file_path=temp_path,
            ),
        )

        result, _ = count_calls_from_file(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # calc.add() should be counted
        assert call_counts[make_qualified_name("__module__.Calculator.add")] == 1


def test_parent_scope_variable_access_in_nested_functions() -> None:
    """Test that nested functions can access parent scope variables."""
    code = """
class Calculator:
    def add(self, a, b):
        return a + b

def outer():
    calc = Calculator()

    def inner():
        return calc.add(1, 2)  # Should be counted

    return inner()
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            make_function_info(
                "add",
                qualified_name=make_qualified_name("__module__.Calculator.add"),
                parameters=(
                    make_parameter("self"),
                    make_parameter("a"),
                    make_parameter("b"),
                ),
                line_number=3,
                file_path=temp_path,
            ),
        )

        result, _ = count_calls_from_file(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # Inner function's use of calc.add() should be counted
        assert call_counts[make_qualified_name("__module__.Calculator.add")] == 1
