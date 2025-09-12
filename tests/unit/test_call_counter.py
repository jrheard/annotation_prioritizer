"""Tests for call counting functionality."""

import ast
import tempfile
from pathlib import Path

from annotation_prioritizer.call_counter import CallCountVisitor, count_function_calls
from annotation_prioritizer.models import FunctionInfo, ParameterInfo


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

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        temp_path = f.name

    try:
        known_functions = (
            FunctionInfo(
                name="func_a",
                qualified_name="func_a",
                parameters=(),
                has_return_annotation=False,
                line_number=2,
                file_path=temp_path,
            ),
            FunctionInfo(
                name="func_b",
                qualified_name="func_b",
                parameters=(),
                has_return_annotation=False,
                line_number=5,
                file_path=temp_path,
            ),
            FunctionInfo(
                name="caller",
                qualified_name="caller",
                parameters=(),
                has_return_annotation=False,
                line_number=8,
                file_path=temp_path,
            ),
        )

        result = count_function_calls(temp_path, known_functions)

        # Convert to dict for easier testing
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        assert call_counts["func_a"] == 3  # Called 3 times
        assert call_counts["func_b"] == 2  # Called 2 times
        assert call_counts["caller"] == 0  # Not called

    finally:
        Path(temp_path).unlink()


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

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        temp_path = f.name

    try:
        known_functions = (
            FunctionInfo(
                name="add",
                qualified_name="Calculator.add",
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
                qualified_name="Calculator.multiply",
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
        assert call_counts["Calculator.add"] == 2
        assert call_counts["Calculator.multiply"] == 1

    finally:
        Path(temp_path).unlink()


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

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        temp_path = f.name

    try:
        known_functions = (
            FunctionInfo(
                name="format_number",
                qualified_name="Utils.format_number",
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
        assert call_counts["Utils.format_number"] == 2

    finally:
        Path(temp_path).unlink()


def test_count_no_calls() -> None:
    """Test with functions that are never called."""
    code = """
def unused_function():
    pass

def another_unused():
    pass
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        temp_path = f.name

    try:
        known_functions = (
            FunctionInfo(
                name="unused_function",
                qualified_name="unused_function",
                parameters=(),
                has_return_annotation=False,
                line_number=2,
                file_path=temp_path,
            ),
            FunctionInfo(
                name="another_unused",
                qualified_name="another_unused",
                parameters=(),
                has_return_annotation=False,
                line_number=5,
                file_path=temp_path,
            ),
        )

        result = count_function_calls(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        assert call_counts["unused_function"] == 0
        assert call_counts["another_unused"] == 0

    finally:
        Path(temp_path).unlink()


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

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        temp_path = f.name

    try:
        known_functions = (
            FunctionInfo(
                name="known_func",
                qualified_name="known_func",
                parameters=(),
                has_return_annotation=False,
                line_number=2,
                file_path=temp_path,
            ),
        )

        result = count_function_calls(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        assert call_counts["known_func"] == 1

    finally:
        Path(temp_path).unlink()


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

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        temp_path = f.name

    try:
        result = count_function_calls(temp_path, ())
        assert result == ()

    finally:
        Path(temp_path).unlink()


def test_count_calls_empty_known_functions() -> None:
    """Test with empty known functions list."""
    code = """
def some_function():
    pass
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        temp_path = f.name

    try:
        result = count_function_calls(temp_path, ())
        assert result == ()

    finally:
        Path(temp_path).unlink()


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

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        temp_path = f.name

    try:
        known_functions = (
            FunctionInfo(
                name="inner_method",
                qualified_name="Outer.Inner.inner_method",
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
        assert call_counts["Outer.Inner.inner_method"] == 0

    finally:
        Path(temp_path).unlink()


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

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        temp_path = f.name

    try:
        known_functions = (
            FunctionInfo(
                name="method_in_class",
                qualified_name="MyClass.method_in_class",
                parameters=(
                    ParameterInfo(name="self", has_annotation=False, is_variadic=False, is_keyword=False),
                ),
                has_return_annotation=False,
                line_number=3,
                file_path=temp_path,
            ),
            FunctionInfo(
                name="standalone_method",
                qualified_name="standalone_method",
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
        assert call_counts["MyClass.method_in_class"] == 0
        assert call_counts["standalone_method"] == 0

    finally:
        Path(temp_path).unlink()


def test_self_call_outside_class_context() -> None:
    """Test self.method() calls that occur outside class context."""
    code = """
# This is invalid Python but tests our edge case handling
def some_function():
    # Imagine this somehow has self.unknown_method() - should not crash
    pass
"""

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
        f.write(code)
        temp_path = f.name

    try:
        # Create a visitor and manually test the edge case
        call_counts = {"method": 0}
        visitor = CallCountVisitor(call_counts)

        # Create a mock Call node that represents self.method() outside class
        func_node = ast.Attribute(value=ast.Name(id="self", ctx=ast.Load()), attr="method", ctx=ast.Load())
        call_node = ast.Call(func=func_node, args=[], keywords=[])

        # Test by actually visiting the call - this should increment the count
        visitor.visit_Call(call_node)
        assert call_counts["method"] == 1  # This covers line 70

    finally:
        Path(temp_path).unlink()


def test_complex_qualified_calls() -> None:
    """Test complex qualified calls to cover line 81."""
    # Create a visitor and manually test the complex qualified call case
    call_counts = {"method": 0}
    visitor = CallCountVisitor(call_counts)

    # Create a mock Call node that represents outer.inner.method()
    # This creates: outer.inner.method() where func.value is ast.Attribute
    inner_attr = ast.Attribute(value=ast.Name(id="outer", ctx=ast.Load()), attr="inner", ctx=ast.Load())
    func_node = ast.Attribute(value=inner_attr, attr="method", ctx=ast.Load())
    call_node = ast.Call(func=func_node, args=[], keywords=[])

    # Test by actually visiting the call - this should increment the count
    visitor.visit_Call(call_node)
    assert call_counts["method"] == 1  # This covers line 81
