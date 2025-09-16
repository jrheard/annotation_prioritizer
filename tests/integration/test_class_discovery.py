"""Integration tests for class detection improvements."""

from annotation_prioritizer.analyzer import analyze_file
from annotation_prioritizer.call_counter import count_function_calls
from annotation_prioritizer.function_parser import parse_function_definitions
from tests.helpers.temp_files import temp_python_file


def test_false_positive_elimination() -> None:
    """Test that constants are not treated as classes."""
    code = """
MAX_SIZE = 100
DEFAULT_CONFIG = {}
PI = 3.14

def use_constants():
    MAX_SIZE.bit_length()  # Should NOT be counted as class method
    DEFAULT_CONFIG.get("key")  # Should NOT be counted
    int.from_bytes(b"test", "big")  # Should be counted (int is built-in)
    return None

class Calculator:
    def add(self, a, b):
        return a + b

def use_class():
    return Calculator.add(None, 1, 2)  # Should be counted
"""

    with temp_python_file(code) as temp_path:
        functions = parse_function_definitions(temp_path)
        counts = count_function_calls(temp_path, functions)

        call_counts = {c.function_qualified_name: c.call_count for c in counts}

        # int.from_bytes is not in our known functions, so won't be counted
        # Calculator.add should be counted
        assert call_counts.get("__module__.Calculator.add", 0) == 1
        # use_constants and use_class should not be called
        assert call_counts.get("__module__.use_constants", 0) == 0
        assert call_counts.get("__module__.use_class", 0) == 0


def test_non_pep8_class_names() -> None:
    """Test that non-PEP8 class names are correctly identified."""
    code = """
class xmlParser:
    def parse(self, data):
        return data

class dataProcessor:
    def process(self, data):
        return self.validate(data)

    def validate(self, data):
        return data

def use_classes():
    xmlParser.parse(None, "<xml>")  # Should be counted
    dataProcessor.process(None, "data")  # Should be counted
"""

    with temp_python_file(code) as temp_path:
        functions = parse_function_definitions(temp_path)
        counts = count_function_calls(temp_path, functions)

        call_counts = {c.function_qualified_name: c.call_count for c in counts}

        assert call_counts["__module__.xmlParser.parse"] == 1
        assert call_counts["__module__.dataProcessor.process"] == 1
        assert call_counts["__module__.dataProcessor.validate"] == 1  # Called by process


def test_nested_class_method_calls() -> None:
    """Test that nested class method calls are correctly resolved."""
    code = """
class Outer:
    class Inner:
        def process(self):
            return "processing"

    def use_inner(self):
        # Should resolve to __module__.Outer.Inner.process
        return Outer.Inner.process(None)

def use_at_module():
    # This will be counted
    return Outer.Inner.process(None)
"""

    with temp_python_file(code) as temp_path:
        functions = parse_function_definitions(temp_path)
        counts = count_function_calls(temp_path, functions)

        call_counts = {c.function_qualified_name: c.call_count for c in counts}

        # Both calls to Outer.Inner.process should be counted
        assert call_counts["__module__.Outer.Inner.process"] == 2


def test_builtin_type_method_calls() -> None:
    """Test that built-in type methods are recognized."""
    code = """
def use_builtins():
    int.from_bytes(b"test", "big")  # Should be recognized as int class
    str.format("template", arg="value")  # Should be recognized as str class
    dict.fromkeys(["a", "b"])  # Should be recognized as dict class
    list.append([], "item")  # Should be recognized as list class

    # These are instance methods, not class methods, so won't be counted
    x = 42
    x.bit_length()  # Instance method, not counted
"""

    with temp_python_file(code) as temp_path:
        functions = parse_function_definitions(temp_path)
        counts = count_function_calls(temp_path, functions)

        # Since we don't track built-in methods in known_functions,
        # none of these will appear in the counts
        # But they won't cause false positives either
        call_counts = {c.function_qualified_name: c.call_count for c in counts}
        assert call_counts.get("__module__.use_builtins", 0) == 0


def test_imported_classes_not_counted() -> None:
    """Verify that imported classes are not recognized (temporary behavior)."""
    code = """
from typing import List
from collections import defaultdict
import math

def use_imports():
    List.append([], "item")  # Should NOT be counted (imported)
    defaultdict.fromkeys([1, 2])  # Should NOT be counted (imported)
    math.sqrt(16)  # Should NOT be counted (imported)
    int.from_bytes(b"test", "big")  # Built-in, recognized but not in known_functions

class LocalClass:
    def local_method(self):
        return 42

def use_local():
    return LocalClass.local_method(None)  # Should be counted
"""

    with temp_python_file(code) as temp_path:
        functions = parse_function_definitions(temp_path)
        counts = count_function_calls(temp_path, functions)

        call_counts = {c.function_qualified_name: c.call_count for c in counts}

        # Only LocalClass.local_method should be counted
        assert call_counts["__module__.LocalClass.local_method"] == 1
        assert call_counts.get("__module__.use_imports", 0) == 0
        assert call_counts.get("__module__.use_local", 0) == 0


def test_instance_method_calls_not_tracked() -> None:
    """Test that instance method calls via variables are not tracked yet."""
    code = """
class Calculator:
    def add(self, a, b):
        return a + b

    def multiply(self, a, b):
        return a * b

def main():
    calc = Calculator()  # Instance creation
    result1 = calc.add(5, 7)  # Instance method call - NOT tracked
    result2 = calc.multiply(3, 4)  # Instance method call - NOT tracked

    # Class method calls - SHOULD be tracked
    result3 = Calculator.add(None, 1, 2)
    result4 = Calculator.multiply(None, 3, 4)

    return result1 + result2 + result3 + result4
"""

    with temp_python_file(code) as temp_path:
        functions = parse_function_definitions(temp_path)
        counts = count_function_calls(temp_path, functions)

        call_counts = {c.function_qualified_name: c.call_count for c in counts}

        # Only direct class method calls should be counted
        assert call_counts["__module__.Calculator.add"] == 1
        assert call_counts["__module__.Calculator.multiply"] == 1


def test_forward_reference_class() -> None:
    """Test that forward-referenced classes are handled correctly."""
    code = """
def process(calc: "Calculator"):  # Forward reference
    # calc.add won't be tracked (instance method)
    return Calculator.add(None, 1, 2)  # Should be tracked

class Calculator:
    def add(self, a, b):
        return a + b

def use_calculator():
    return Calculator.add(None, 3, 4)  # Should be tracked
"""

    with temp_python_file(code) as temp_path:
        functions = parse_function_definitions(temp_path)
        counts = count_function_calls(temp_path, functions)

        call_counts = {c.function_qualified_name: c.call_count for c in counts}

        # Both Calculator.add calls should be counted
        assert call_counts["__module__.Calculator.add"] == 2


def test_complex_scope_resolution() -> None:
    """Test complex scope resolution for nested classes."""
    code = """
class Outer:
    class Inner:
        def inner_method(self):
            return "inner"

    def use_inner_same_scope(self):
        # Inside Outer, Inner should resolve correctly
        return Outer.Inner.inner_method(None)

    class AnotherInner:
        def another_method(self):
            # From AnotherInner, should still resolve Inner correctly
            return Outer.Inner.inner_method(None)

def module_level_use():
    return Outer.Inner.inner_method(None)
"""

    with temp_python_file(code) as temp_path:
        functions = parse_function_definitions(temp_path)
        counts = count_function_calls(temp_path, functions)

        call_counts = {c.function_qualified_name: c.call_count for c in counts}

        # All three calls to Outer.Inner.inner_method should be counted
        assert call_counts["__module__.Outer.Inner.inner_method"] == 3


def test_camelcase_vs_constants() -> None:
    """Test that camelCase variables are not treated as classes."""
    code = """
myVariable = 100  # camelCase variable
someConfig = {"key": "value"}  # camelCase variable

class MyClass:
    def method(self):
        return 1

def use_stuff():
    # These should NOT be counted (not classes)
    result1 = myVariable.bit_length() if hasattr(myVariable, 'bit_length') else 0
    result2 = someConfig.get("key") if hasattr(someConfig, 'get') else None

    # This SHOULD be counted (actual class)
    result3 = MyClass.method(None)

    return result1, result2, result3
"""

    with temp_python_file(code) as temp_path:
        functions = parse_function_definitions(temp_path)
        counts = count_function_calls(temp_path, functions)

        call_counts = {c.function_qualified_name: c.call_count for c in counts}

        # Only MyClass.method should be counted
        assert call_counts["__module__.MyClass.method"] == 1


def test_class_in_function_scope() -> None:
    """Test classes defined inside functions."""
    code = """
def factory():
    class LocalClass:
        def local_method(self):
            return 42

    # This should be tracked
    result = LocalClass.local_method(None)
    return LocalClass

def another_factory():
    class LocalClass:  # Different LocalClass in different function
        def local_method(self):
            return 100

    # This should also be tracked (different qualified name)
    result = LocalClass.local_method(None)
    return LocalClass
"""

    with temp_python_file(code) as temp_path:
        functions = parse_function_definitions(temp_path)
        counts = count_function_calls(temp_path, functions)

        call_counts = {c.function_qualified_name: c.call_count for c in counts}

        # Each LocalClass.local_method in its respective function scope
        assert call_counts["__module__.factory.LocalClass.local_method"] == 1
        assert call_counts["__module__.another_factory.LocalClass.local_method"] == 1


def test_end_to_end_with_class_detection() -> None:
    """Test complete analysis pipeline with class detection."""
    code = """
MAX_RETRIES = 3
DEFAULT_TIMEOUT = 30

class NetworkClient:
    def connect(self, host: str, port: int):
        return f"Connected to {host}:{port}"

    def send_data(self, data):
        return self.validate(data) and self._transmit(data)

    def validate(self, data):
        return data is not None

    def _transmit(self, data):
        return True

class ErrorHandler:
    def handle_error(self, error):
        return f"Handled: {error}"

def main():
    # These should NOT be counted (constants, not classes)
    retries = MAX_RETRIES.bit_length() if hasattr(MAX_RETRIES, 'bit_length') else 0
    timeout = DEFAULT_TIMEOUT.bit_length() if hasattr(DEFAULT_TIMEOUT, 'bit_length') else 0

    # These SHOULD be counted (actual class methods)
    NetworkClient.connect(None, "localhost", 8080)
    ErrorHandler.handle_error(None, "test error")

    return retries, timeout
"""

    with temp_python_file(code) as temp_path:
        # Full analysis pipeline
        results = analyze_file(temp_path)

        # Check that the right methods were analyzed
        function_names = {fp.function_info.qualified_name for fp in results}

        assert "__module__.NetworkClient.connect" in function_names
        assert "__module__.NetworkClient.send_data" in function_names
        assert "__module__.NetworkClient.validate" in function_names
        assert "__module__.NetworkClient._transmit" in function_names
        assert "__module__.ErrorHandler.handle_error" in function_names
        assert "__module__.main" in function_names

        # Check call counts
        call_counts = {fp.function_info.qualified_name: fp.call_count for fp in results}

        assert call_counts["__module__.NetworkClient.connect"] == 1
        assert call_counts["__module__.NetworkClient.validate"] == 1  # Called by send_data
        assert call_counts["__module__.NetworkClient._transmit"] == 1  # Called by send_data
        assert call_counts["__module__.ErrorHandler.handle_error"] == 1
