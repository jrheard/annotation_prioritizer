"""Tests for the AST parser module."""

from annotation_prioritizer.models import ParameterInfo
from annotation_prioritizer.parser import parse_function_definitions
from tests.helpers.temp_files import temp_python_file


def test_parse_function_definitions_empty_file() -> None:
    """Test parsing an empty Python file."""
    with temp_python_file("") as path:
        result = parse_function_definitions(path)
        assert result == ()


def test_parse_function_definitions_nonexistent_file() -> None:
    """Test parsing a file that doesn't exist."""
    result = parse_function_definitions("/nonexistent/file.py")
    assert result == ()


def test_parse_function_definitions_syntax_error() -> None:
    """Test parsing a file with syntax errors."""
    with temp_python_file("def broken_syntax(\n") as path:
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
        assert func.qualified_name == "simple_function"
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


def test_parse_function_with_varargs() -> None:
    """Test parsing a function with *args and **kwargs."""
    source = """
def varargs_function(a: int, *args: str, **kwargs: bool) -> None:
    pass
"""

    with temp_python_file(source) as path:
        result = parse_function_definitions(path)
        assert len(result) == 1

        func = result[0]
        assert func.has_return_annotation is True
        assert len(func.parameters) == 3

        assert func.parameters[0] == ParameterInfo("a", True, False, False)
        assert func.parameters[1] == ParameterInfo("args", True, True, False)
        assert func.parameters[2] == ParameterInfo("kwargs", True, False, True)


def test_parse_function_with_varargs_no_annotations() -> None:
    """Test parsing a function with *args and **kwargs without annotations."""
    source = """
def varargs_function(a, *args, **kwargs):
    pass
"""

    with temp_python_file(source) as path:
        result = parse_function_definitions(path)
        assert len(result) == 1

        func = result[0]
        assert func.has_return_annotation is False
        assert len(func.parameters) == 3

        assert func.parameters[0] == ParameterInfo("a", False, False, False)
        assert func.parameters[1] == ParameterInfo("args", False, True, False)
        assert func.parameters[2] == ParameterInfo("kwargs", False, False, True)


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
        assert instance_method.qualified_name == "TestClass.instance_method"
        assert instance_method.has_return_annotation is True
        assert len(instance_method.parameters) == 2
        assert instance_method.parameters[0] == ParameterInfo("self", False, False, False)
        assert instance_method.parameters[1] == ParameterInfo("x", True, False, False)

        class_method = next(f for f in result if f.name == "class_method")
        assert class_method.qualified_name == "TestClass.class_method"
        assert class_method.has_return_annotation is True

        static_method = next(f for f in result if f.name == "static_method")
        assert static_method.qualified_name == "TestClass.static_method"
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
        assert outer_method.qualified_name == "OuterClass.outer_method"

        inner_method = next(f for f in result if f.name == "inner_method")
        assert inner_method.qualified_name == "OuterClass.InnerClass.inner_method"


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
        assert async_func.qualified_name == "async_function"
        assert async_func.has_return_annotation is True

        async_method = next(f for f in result if f.name == "async_method")
        assert async_method.qualified_name == "AsyncClass.async_method"
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
        assert qualified_names == {"func1", "func2", "TestClass.method1", "func3"}
