# pyright: reportPrivateUsage=false
"""Tests for call counting functionality."""

import ast

from annotation_prioritizer.call_counter import CallCountVisitor, count_function_calls
from annotation_prioritizer.class_discovery import build_class_registry
from annotation_prioritizer.iteration import first
from annotation_prioritizer.models import FunctionInfo, ParameterInfo, Scope, ScopeKind
from annotation_prioritizer.scope_tracker import add_scope, drop_last_scope
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
            FunctionInfo(
                name="func_a",
                qualified_name="__module__.func_a",
                parameters=(),
                has_return_annotation=False,
                line_number=2,
                file_path=temp_path,
            ),
            FunctionInfo(
                name="func_b",
                qualified_name="__module__.func_b",
                parameters=(),
                has_return_annotation=False,
                line_number=5,
                file_path=temp_path,
            ),
            FunctionInfo(
                name="caller",
                qualified_name="__module__.caller",
                parameters=(),
                has_return_annotation=False,
                line_number=8,
                file_path=temp_path,
            ),
        )

        result = count_function_calls(temp_path, known_functions)

        # Convert to dict for easier testing
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        assert call_counts["__module__.func_a"] == 3  # Called 3 times
        assert call_counts["__module__.func_b"] == 2  # Called 2 times
        assert call_counts["__module__.caller"] == 0  # Not called


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
            FunctionInfo(
                name="add",
                qualified_name="__module__.Calculator.add",
                parameters=(
                    ParameterInfo(name="self", has_annotation=False, is_variadic=False, is_keyword=False),
                    ParameterInfo(name="a", has_annotation=False, is_variadic=False, is_keyword=False),
                    ParameterInfo(name="b", has_annotation=False, is_variadic=False, is_keyword=False),
                ),
                has_return_annotation=False,
                line_number=3,
                file_path=temp_path,
            ),
            FunctionInfo(
                name="multiply",
                qualified_name="__module__.Calculator.multiply",
                parameters=(
                    ParameterInfo(name="self", has_annotation=False, is_variadic=False, is_keyword=False),
                    ParameterInfo(name="a", has_annotation=False, is_variadic=False, is_keyword=False),
                    ParameterInfo(name="b", has_annotation=False, is_variadic=False, is_keyword=False),
                ),
                has_return_annotation=False,
                line_number=6,
                file_path=temp_path,
            ),
        )

        result = count_function_calls(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # self.add() called twice in calculate method + once in use_calculator = 3 times
        # But we can't track the external call to calc.add() because it's not self.add()
        # So we should only count self.add() calls = 2 times
        assert call_counts["__module__.Calculator.add"] == 2
        assert call_counts["__module__.Calculator.multiply"] == 1


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
            FunctionInfo(
                name="format_number",
                qualified_name="__module__.Utils.format_number",
                parameters=(
                    ParameterInfo(name="n", has_annotation=False, is_variadic=False, is_keyword=False),
                ),
                has_return_annotation=False,
                line_number=4,
                file_path=temp_path,
            ),
        )

        result = count_function_calls(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # Utils.format_number() called twice
        assert call_counts["__module__.Utils.format_number"] == 2


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
            FunctionInfo(
                name="unused_function",
                qualified_name="__module__.unused_function",
                parameters=(),
                has_return_annotation=False,
                line_number=2,
                file_path=temp_path,
            ),
            FunctionInfo(
                name="another_unused",
                qualified_name="__module__.another_unused",
                parameters=(),
                has_return_annotation=False,
                line_number=5,
                file_path=temp_path,
            ),
        )

        result = count_function_calls(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        assert call_counts["__module__.unused_function"] == 0
        assert call_counts["__module__.another_unused"] == 0


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
            FunctionInfo(
                name="known_func",
                qualified_name="__module__.known_func",
                parameters=(),
                has_return_annotation=False,
                line_number=2,
                file_path=temp_path,
            ),
        )

        result = count_function_calls(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        assert call_counts["__module__.known_func"] == 1


def test_count_calls_nonexistent_file() -> None:
    """Test handling of nonexistent files."""
    result = count_function_calls("/nonexistent/file.py", ())
    assert result == ()


def test_count_calls_syntax_error() -> None:
    """Test handling of files with syntax errors."""
    code = """
def broken_syntax(
    # Missing closing parenthesis
"""

    with temp_python_file(code) as temp_path:
        result = count_function_calls(temp_path, ())
        assert result == ()


def test_count_calls_empty_known_functions() -> None:
    """Test with empty known functions list."""
    code = """
def some_function():
    pass
"""

    with temp_python_file(code) as temp_path:
        result = count_function_calls(temp_path, ())
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
            FunctionInfo(
                name="inner_method",
                qualified_name="__module__.Outer.Inner.inner_method",
                parameters=(
                    ParameterInfo(name="self", has_annotation=False, is_variadic=False, is_keyword=False),
                ),
                has_return_annotation=False,
                line_number=4,
                file_path=temp_path,
            ),
        )

        result = count_function_calls(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # Due to our simple implementation, these complex calls won't be tracked
        assert call_counts["__module__.Outer.Inner.inner_method"] == 0


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
            FunctionInfo(
                name="method_in_class",
                qualified_name="__module__.MyClass.method_in_class",
                parameters=(
                    ParameterInfo(name="self", has_annotation=False, is_variadic=False, is_keyword=False),
                ),
                has_return_annotation=False,
                line_number=3,
                file_path=temp_path,
            ),
            FunctionInfo(
                name="standalone_method",
                qualified_name="__module__.standalone_method",
                parameters=(),
                has_return_annotation=False,
                line_number=12,
                file_path=temp_path,
            ),
        )

        result = count_function_calls(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # The obj.method_in_class() call won't match our known function because
        # it's not self.method_in_class(), so count should be 0
        assert call_counts["__module__.MyClass.method_in_class"] == 0
        assert call_counts["__module__.standalone_method"] == 0


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
        FunctionInfo(
            name="method",
            qualified_name="__module__.method",
            parameters=(),
            has_return_annotation=False,
            line_number=1,
            file_path="dummy.py",
        ),
    )

    class_registry = build_class_registry(ast.parse(""))
    visitor = CallCountVisitor(known_functions, class_registry)

    # Test by visiting the call - this should increment the count
    visitor.visit_Call(call_node)
    assert visitor.call_counts["__module__.method"] == 1  # This covers line 70


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
        FunctionInfo(
            name="method",
            qualified_name="__module__.method",
            parameters=(),
            has_return_annotation=False,
            line_number=1,
            file_path="dummy.py",
        ),
    )

    class_registry = build_class_registry(ast.parse(""))
    visitor = CallCountVisitor(known_functions, class_registry)

    # Test by visiting the call - unresolved references should not be counted
    visitor.visit_Call(call_node)
    assert visitor.call_counts["__module__.method"] == 0  # Unresolved compound name not counted


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
            FunctionInfo(
                name="outer_function",
                qualified_name="__module__.outer_function",
                parameters=(),
                has_return_annotation=False,
                line_number=2,
                file_path=temp_path,
            ),
            FunctionInfo(
                name="inner_function",
                qualified_name="__module__.outer_function.inner_function",
                parameters=(),
                has_return_annotation=False,
                line_number=3,
                file_path=temp_path,
            ),
            FunctionInfo(
                name="another_inner",
                qualified_name="__module__.outer_function.another_inner",
                parameters=(),
                has_return_annotation=False,
                line_number=6,
                file_path=temp_path,
            ),
            FunctionInfo(
                name="helper_function",
                qualified_name="__module__.helper_function",
                parameters=(),
                has_return_annotation=False,
                line_number=11,
                file_path=temp_path,
            ),
        )

        result = count_function_calls(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # outer_function() called:
        # - once from inner_function
        # - once from top_level_caller
        # Total: 2 calls
        assert call_counts["__module__.outer_function"] == 2

        # inner_function() called:
        # - once from another_inner
        # - once from outer_function itself
        # Total: 2 calls
        assert call_counts["__module__.outer_function.inner_function"] == 2

        # another_inner() called:
        # - once from outer_function
        # Total: 1 call
        assert call_counts["__module__.outer_function.another_inner"] == 1

        # helper_function() called:
        # - once from another_inner
        # - once from top_level_caller
        # Total: 2 calls
        assert call_counts["__module__.helper_function"] == 2


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
            FunctionInfo(
                name="add",
                qualified_name="__module__.Calculator.add",
                parameters=(
                    ParameterInfo(name="self", has_annotation=False, is_variadic=False, is_keyword=False),
                    ParameterInfo(name="a", has_annotation=False, is_variadic=False, is_keyword=False),
                    ParameterInfo(name="b", has_annotation=False, is_variadic=False, is_keyword=False),
                ),
                has_return_annotation=False,
                line_number=14,
                file_path=temp_path,
            ),
            FunctionInfo(
                name="multiply",
                qualified_name="__module__.Calculator.multiply",
                parameters=(
                    ParameterInfo(name="self", has_annotation=False, is_variadic=False, is_keyword=False),
                    ParameterInfo(name="a", has_annotation=False, is_variadic=False, is_keyword=False),
                    ParameterInfo(name="b", has_annotation=False, is_variadic=False, is_keyword=False),
                ),
                has_return_annotation=False,
                line_number=17,
                file_path=temp_path,
            ),
        )

        result = count_function_calls(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # self.add() called:
        # - once from inner_helper nested function
        # - once from complex_operation directly
        # Total: 2 calls
        assert call_counts["__module__.Calculator.add"] == 2

        # self.multiply() called:
        # - once from another_helper nested function
        # Total: 1 call
        assert call_counts["__module__.Calculator.multiply"] == 1


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
            FunctionInfo(
                name="helper_method",
                qualified_name="__module__.OuterClass.helper_method",
                parameters=(
                    ParameterInfo(name="self", has_annotation=False, is_variadic=False, is_keyword=False),
                ),
                has_return_annotation=False,
                line_number=10,
                file_path=temp_path,
            ),
            FunctionInfo(
                name="module_function",
                qualified_name="__module__.module_function",
                parameters=(),
                has_return_annotation=False,
                line_number=13,
                file_path=temp_path,
            ),
        )

        result = count_function_calls(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # self.helper_method() called once from level3_function
        assert call_counts["__module__.OuterClass.helper_method"] == 1

        # module_function() called once from level2_function
        assert call_counts["__module__.module_function"] == 1


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
            FunctionInfo(
                name="other_inner_method",
                qualified_name="__module__.Outer.Inner.other_inner_method",
                parameters=(
                    ParameterInfo(name="self", has_annotation=False, is_variadic=False, is_keyword=False),
                ),
                has_return_annotation=False,
                line_number=8,
                file_path=temp_path,
            ),
            FunctionInfo(
                name="module_helper",
                qualified_name="__module__.module_helper",
                parameters=(),
                has_return_annotation=False,
                line_number=11,
                file_path=temp_path,
            ),
        )

        result = count_function_calls(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # self.other_inner_method() called once from inner_method
        assert call_counts["__module__.Outer.Inner.other_inner_method"] == 1

        # module_helper() called once from nested_function
        assert call_counts["__module__.module_helper"] == 1


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
    visitor = CallCountVisitor((), class_registry)

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

    visitor = CallCountVisitor((), class_registry)

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
        FunctionInfo(
            name="method",
            qualified_name="__module__.my_function.Outer.Inner.method",
            parameters=(),
            has_return_annotation=False,
            line_number=5,
            file_path="test.py",
        ),
    )

    visitor = CallCountVisitor(known_functions, class_registry)
    visitor.visit(tree)

    assert visitor.call_counts["__module__.my_function.Outer.Inner.method"] == 1


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
            FunctionInfo(
                name="async_outer",
                qualified_name="__module__.async_outer",
                parameters=(),
                has_return_annotation=False,
                line_number=2,
                file_path=temp_path,
            ),
            FunctionInfo(
                name="async_inner",
                qualified_name="__module__.async_outer.async_inner",
                parameters=(),
                has_return_annotation=False,
                line_number=3,
                file_path=temp_path,
            ),
            FunctionInfo(
                name="regular_helper",
                qualified_name="__module__.regular_helper",
                parameters=(),
                has_return_annotation=False,
                line_number=12,
                file_path=temp_path,
            ),
        )

        result = count_function_calls(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # async_outer() called:
        # - once from async_inner (await async_outer())
        # - once from top_level_async (await async_outer())
        # Total: 2 calls
        assert call_counts["__module__.async_outer"] == 2

        # async_inner() called:
        # - once from async_outer (await async_inner())
        # Total: 1 call
        assert call_counts["__module__.async_outer.async_inner"] == 1

        # regular_helper() called:
        # - once from sync_inner nested function
        # - once from top_level_async
        # Total: 2 calls
        assert call_counts["__module__.regular_helper"] == 2


def test_builtin_shadowing() -> None:
    """Test that local classes shadow builtin types in name resolution."""
    code = """
class list:  # Shadows builtin list
    @staticmethod
    def append(item):
        pass

def test():
    list.append("x")  # Should resolve to local list, not builtin
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            FunctionInfo(
                name="append",
                qualified_name="__module__.list.append",  # Local class method
                parameters=(
                    ParameterInfo(name="item", has_annotation=False, is_variadic=False, is_keyword=False),
                ),
                has_return_annotation=False,
                line_number=4,
                file_path=temp_path,
            ),
            FunctionInfo(
                name="append",
                qualified_name="list.append",  # Builtin list.append
                parameters=(
                    ParameterInfo(name="self", has_annotation=False, is_variadic=False, is_keyword=False),
                    ParameterInfo(name="item", has_annotation=False, is_variadic=False, is_keyword=False),
                ),
                has_return_annotation=False,
                line_number=1,
                file_path=temp_path,
            ),
        )

        result = count_function_calls(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # Local class method should be called, not builtin
        assert call_counts["__module__.list.append"] == 1
        assert call_counts["list.append"] == 0


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
            FunctionInfo(
                name="method",
                qualified_name="__module__.MyClass.method",
                parameters=(
                    ParameterInfo(name="self", has_annotation=False, is_variadic=False, is_keyword=False),
                ),
                has_return_annotation=False,
                line_number=3,
                file_path=temp_path,
            ),
        )

        # Should not crash, just return 0 calls since we can't resolve complex expressions
        result = count_function_calls(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        assert call_counts["__module__.MyClass.method"] == 0


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
            FunctionInfo(
                name="method",
                qualified_name="__module__.KnownClass.method",
                parameters=(
                    ParameterInfo(name="self", has_annotation=False, is_variadic=False, is_keyword=False),
                ),
                has_return_annotation=False,
                line_number=3,
                file_path=temp_path,
            ),
        )

        result = count_function_calls(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # None of the unresolvable references should be counted
        assert call_counts["__module__.KnownClass.method"] == 0
