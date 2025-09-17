"""Tests for the AST parser module."""

import pytest

from annotation_prioritizer.function_parser import parse_function_definitions
from annotation_prioritizer.models import ParameterInfo, make_qualified_name
from tests.helpers.temp_files import temp_python_file


@pytest.mark.parametrize(
    ("test_case", "file_content"),
    [
        ("empty_file", ""),
        ("nonexistent_file", None),
        ("syntax_error", "def broken_syntax(\n"),
    ],
)
def test_parse_invalid_inputs_return_empty(test_case: str, file_content: str | None) -> None:
    """Test that parser returns empty tuple for various invalid inputs."""
    if test_case == "nonexistent_file":
        result = parse_function_definitions("/nonexistent/file.py")
    else:
        assert file_content is not None  # Type narrowing for pyright
        with temp_python_file(file_content) as path:
            result = parse_function_definitions(path)

    assert result == ()


def test_parse_simple_function_no_annotations() -> None:
    """Test parsing a simple function without annotations."""
    source = """
def simple_function(a, b):
    return a + b
"""

    with temp_python_file(source) as path:
        result = parse_function_definitions(path)
        assert len(result) == 1

        func = result[0]
        assert func.name == "simple_function"
        assert func.qualified_name == make_qualified_name("__module__.simple_function")
        assert func.has_return_annotation is False
        assert func.line_number == 2
        assert func.file_path == path

        assert len(func.parameters) == 2
        assert func.parameters[0] == ParameterInfo("a", False, False, False)
        assert func.parameters[1] == ParameterInfo("b", False, False, False)


def test_parse_function_with_annotations() -> None:
    """Test parsing a function with type annotations."""
    source = """
def annotated_function(a: int, b: str) -> bool:
    return len(b) > a
"""

    with temp_python_file(source) as path:
        result = parse_function_definitions(path)
        assert len(result) == 1

        func = result[0]
        assert func.name == "annotated_function"
        assert func.has_return_annotation is True

        assert len(func.parameters) == 2
        assert func.parameters[0] == ParameterInfo("a", True, False, False)
        assert func.parameters[1] == ParameterInfo("b", True, False, False)


def test_parse_function_mixed_annotations() -> None:
    """Test parsing a function with mixed annotation coverage."""
    source = """
def mixed_function(a: int, b, c: str):
    pass
"""

    with temp_python_file(source) as path:
        result = parse_function_definitions(path)
        assert len(result) == 1

        func = result[0]
        assert len(func.parameters) == 3
        assert func.parameters[0] == ParameterInfo("a", True, False, False)
        assert func.parameters[1] == ParameterInfo("b", False, False, False)
        assert func.parameters[2] == ParameterInfo("c", True, False, False)


@pytest.mark.parametrize(
    ("with_annotations", "expected_annotations"),
    [
        (True, {"a": True, "args": True, "kwargs": True, "return": True}),
        (False, {"a": False, "args": False, "kwargs": False, "return": False}),
    ],
)
def test_parse_function_with_varargs(
    *, with_annotations: bool, expected_annotations: dict[str, bool]
) -> None:
    """Test parsing functions with *args and **kwargs with and without annotations."""
    if with_annotations:
        source = """
def varargs_function(a: int, *args: str, **kwargs: bool) -> None:
    pass
"""
    else:
        source = """
def varargs_function(a, *args, **kwargs):
    pass
"""

    with temp_python_file(source) as path:
        result = parse_function_definitions(path)
        assert len(result) == 1

        func = result[0]
        assert func.has_return_annotation is expected_annotations["return"]
        assert len(func.parameters) == 3

        assert func.parameters[0] == ParameterInfo("a", expected_annotations["a"], False, False)
        assert func.parameters[1] == ParameterInfo("args", expected_annotations["args"], True, False)
        assert func.parameters[2] == ParameterInfo("kwargs", expected_annotations["kwargs"], False, True)


def test_parse_class_methods() -> None:
    """Test parsing methods within a class."""
    source = """
class TestClass:
    def instance_method(self, x: int) -> str:
        return str(x)

    @classmethod
    def class_method(cls, y) -> None:
        pass

    @staticmethod
    def static_method(z: bool):
        return not z
"""

    with temp_python_file(source) as path:
        result = parse_function_definitions(path)
        assert len(result) == 3

        # Check qualified names
        instance_method = next(f for f in result if f.name == "instance_method")
        assert instance_method.qualified_name == make_qualified_name("__module__.TestClass.instance_method")
        assert instance_method.has_return_annotation is True
        assert len(instance_method.parameters) == 2
        assert instance_method.parameters[0] == ParameterInfo("self", False, False, False)
        assert instance_method.parameters[1] == ParameterInfo("x", True, False, False)

        class_method = next(f for f in result if f.name == "class_method")
        assert class_method.qualified_name == make_qualified_name("__module__.TestClass.class_method")
        assert class_method.has_return_annotation is True

        static_method = next(f for f in result if f.name == "static_method")
        assert static_method.qualified_name == make_qualified_name("__module__.TestClass.static_method")
        assert static_method.has_return_annotation is False


def test_parse_nested_classes() -> None:
    """Test parsing methods in nested classes."""
    source = """
class OuterClass:
    def outer_method(self):
        pass

    class InnerClass:
        def inner_method(self, x: int):
            return x
"""

    with temp_python_file(source) as path:
        result = parse_function_definitions(path)
        assert len(result) == 2

        outer_method = next(f for f in result if f.name == "outer_method")
        assert outer_method.qualified_name == make_qualified_name("__module__.OuterClass.outer_method")

        inner_method = next(f for f in result if f.name == "inner_method")
        assert inner_method.qualified_name == make_qualified_name(
            "__module__.OuterClass.InnerClass.inner_method"
        )


def test_parse_async_functions() -> None:
    """Test parsing async functions."""
    source = """
async def async_function(x: int) -> str:
    return str(x)

class AsyncClass:
    async def async_method(self):
        pass
"""

    with temp_python_file(source) as path:
        result = parse_function_definitions(path)
        assert len(result) == 2

        async_func = next(f for f in result if f.name == "async_function")
        assert async_func.qualified_name == make_qualified_name("__module__.async_function")
        assert async_func.has_return_annotation is True

        async_method = next(f for f in result if f.name == "async_method")
        assert async_method.qualified_name == make_qualified_name("__module__.AsyncClass.async_method")
        assert async_method.has_return_annotation is False


def test_parse_keyword_only_args() -> None:
    """Test parsing functions with keyword-only arguments."""
    source = """
def keyword_only(a, *, b: int, c) -> None:
    pass
"""

    with temp_python_file(source) as path:
        result = parse_function_definitions(path)
        assert len(result) == 1

        func = result[0]
        assert len(func.parameters) == 3
        assert func.parameters[0] == ParameterInfo("a", False, False, False)
        assert func.parameters[1] == ParameterInfo("b", True, False, False)
        assert func.parameters[2] == ParameterInfo("c", False, False, False)


def test_parse_no_parameters() -> None:
    """Test parsing a function with no parameters."""
    source = """
def no_params() -> int:
    return 42
"""

    with temp_python_file(source) as path:
        result = parse_function_definitions(path)
        assert len(result) == 1

        func = result[0]
        assert func.name == "no_params"
        assert len(func.parameters) == 0
        assert func.has_return_annotation is True


def test_parse_multiple_functions() -> None:
    """Test parsing multiple functions in the same file."""
    source = """
def func1():
    pass

def func2(x: int):
    return x

class TestClass:
    def method1(self):
        pass

def func3() -> str:
    return "test"
"""

    with temp_python_file(source) as path:
        result = parse_function_definitions(path)
        assert len(result) == 4

        names = {f.name for f in result}
        assert names == {"func1", "func2", "method1", "func3"}

        qualified_names = {f.qualified_name for f in result}
        assert qualified_names == {
            "__module__.func1",
            "__module__.func2",
            "__module__.TestClass.method1",
            "__module__.func3",
        }


def test_parse_nested_functions() -> None:
    """Test parsing functions nested inside other functions."""
    source = """
def outer_function(x):
    def inner_function(y):
        return y + 1

    def another_inner(z: int) -> str:
        return str(z)

    return inner_function(x)
"""

    with temp_python_file(source) as path:
        result = parse_function_definitions(path)
        assert len(result) == 3

        # Check all functions are found
        names = {f.name for f in result}
        assert names == {"outer_function", "inner_function", "another_inner"}

        # Check qualified names include the nesting
        qualified_names = {f.qualified_name for f in result}
        assert qualified_names == {
            "__module__.outer_function",
            "__module__.outer_function.inner_function",
            "__module__.outer_function.another_inner",
        }

        # Verify specific function details
        outer_func = next(f for f in result if f.name == "outer_function")
        assert outer_func.qualified_name == make_qualified_name("__module__.outer_function")
        assert outer_func.has_return_annotation is False

        inner_func = next(f for f in result if f.name == "inner_function")
        assert inner_func.qualified_name == make_qualified_name("__module__.outer_function.inner_function")
        assert inner_func.has_return_annotation is False

        another_inner = next(f for f in result if f.name == "another_inner")
        assert another_inner.qualified_name == make_qualified_name("__module__.outer_function.another_inner")
        assert another_inner.has_return_annotation is True


def test_parse_functions_in_nested_classes() -> None:
    """Test parsing functions defined inside methods of nested classes."""
    source = """
class Outer:
    def outer_method(self):
        def nested_func():
            pass
        return nested_func

    class Inner:
        def inner_method(self, x: int):
            def deeply_nested(y):
                return y * 2
            return deeply_nested(x)
"""

    with temp_python_file(source) as path:
        result = parse_function_definitions(path)
        assert len(result) == 4

        # Check all functions are found
        names = {f.name for f in result}
        assert names == {"outer_method", "nested_func", "inner_method", "deeply_nested"}

        # Check qualified names
        qualified_names = {f.qualified_name for f in result}
        assert qualified_names == {
            "__module__.Outer.outer_method",
            "__module__.Outer.outer_method.nested_func",
            "__module__.Outer.Inner.inner_method",
            "__module__.Outer.Inner.inner_method.deeply_nested",
        }


def test_parse_classes_in_functions() -> None:
    """Test parsing classes defined inside functions."""
    source = """
def factory_function():
    class LocalClass:
        def local_method(self, data: str) -> int:
            return len(data)

        def another_method(self):
            def inner_func():
                pass
            return inner_func

    return LocalClass
"""

    with temp_python_file(source) as path:
        result = parse_function_definitions(path)
        assert len(result) == 4

        # Check all functions are found
        names = {f.name for f in result}
        assert names == {"factory_function", "local_method", "another_method", "inner_func"}

        # Check qualified names
        qualified_names = {f.qualified_name for f in result}
        assert qualified_names == {
            "__module__.factory_function",
            "__module__.factory_function.LocalClass.local_method",
            "__module__.factory_function.LocalClass.another_method",
            "__module__.factory_function.LocalClass.another_method.inner_func",
        }

        # Verify the annotations are preserved
        local_method = next(f for f in result if f.name == "local_method")
        assert local_method.has_return_annotation is True
        assert len(local_method.parameters) == 2
        assert local_method.parameters[1].has_annotation is True


def test_parse_deeply_nested_structure() -> None:
    """Test parsing a deeply nested structure with mixed classes and functions."""
    source = """
class OuterClass:
    def method1(self):
        def inner_func():
            class InnerClass:
                def inner_method(self):
                    def deeply_nested():
                        pass
                    return deeply_nested
            return InnerClass
        return inner_func

    class NestedClass:
        def nested_method(self):
            pass
"""

    with temp_python_file(source) as path:
        result = parse_function_definitions(path)
        assert len(result) == 5

        # Check all functions are found
        names = {f.name for f in result}
        assert names == {"method1", "inner_func", "inner_method", "deeply_nested", "nested_method"}

        # Check qualified names reflect the complete nesting
        qualified_names = {f.qualified_name for f in result}
        assert qualified_names == {
            "__module__.OuterClass.method1",
            "__module__.OuterClass.method1.inner_func",
            "__module__.OuterClass.method1.inner_func.InnerClass.inner_method",
            "__module__.OuterClass.method1.inner_func.InnerClass.inner_method.deeply_nested",
            "__module__.OuterClass.NestedClass.nested_method",
        }


def test_parse_async_nested_functions() -> None:
    """Test parsing async functions in nested contexts."""
    source = """
async def async_outer():
    async def async_inner():
        return "inner"

    def sync_inner():
        async def async_deeply_nested():
            pass
        return async_deeply_nested

    return await async_inner()

class AsyncClass:
    async def async_method(self):
        def nested_in_async():
            pass
        return nested_in_async
"""

    with temp_python_file(source) as path:
        result = parse_function_definitions(path)
        assert len(result) == 6

        # Check all functions are found
        names = {f.name for f in result}
        assert names == {
            "async_outer",
            "async_inner",
            "sync_inner",
            "async_deeply_nested",
            "async_method",
            "nested_in_async",
        }

        # Check qualified names
        qualified_names = {f.qualified_name for f in result}
        assert qualified_names == {
            "__module__.async_outer",
            "__module__.async_outer.async_inner",
            "__module__.async_outer.sync_inner",
            "__module__.async_outer.sync_inner.async_deeply_nested",
            "__module__.AsyncClass.async_method",
            "__module__.AsyncClass.async_method.nested_in_async",
        }
