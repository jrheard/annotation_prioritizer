"""Integration tests for class_discovery.py's functionality."""

from annotation_prioritizer.analyzer import analyze_file
from annotation_prioritizer.models import make_qualified_name
from tests.helpers.function_parsing import count_calls_from_file, parse_functions_from_file
from tests.helpers.temp_files import temp_python_file


def test_false_positive_elimination() -> None:
    """Test that constants and built-in types are not treated as user-defined classes."""
    code = """
MAX_SIZE = 100
DEFAULT_CONFIG = {}
PI = 3.14

def use_constants():
    MAX_SIZE.bit_length()  # Constant, not a class method - NOT counted
    DEFAULT_CONFIG.get("key")  # Constant, not a class method - NOT counted
    int.from_bytes(b"test", "big")  # Built-in class method - NOT counted (not in known_functions)
    return None

class Calculator:
    def add(self, a, b):
        return a + b

def use_class():
    return Calculator.add(None, 1, 2)  # User-defined class method - WILL be counted
"""

    with temp_python_file(code) as temp_path:
        functions = parse_functions_from_file(temp_path)
        counts, _ = count_calls_from_file(temp_path, functions)

        call_counts = {c.function_qualified_name: c.call_count for c in counts}

        # Only user-defined class methods are counted
        assert call_counts.get(make_qualified_name("__module__.Calculator.add"), 0) == 1

        # Built-in class methods like int.from_bytes are NOT counted
        # (they're not in known_functions since they're not defined in this file)
        assert "int.from_bytes" not in call_counts
        assert "__builtins__.int.from_bytes" not in call_counts

        # These functions are not called
        assert call_counts.get(make_qualified_name("__module__.use_constants"), 0) == 0
        assert call_counts.get(make_qualified_name("__module__.use_class"), 0) == 0


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
        functions = parse_functions_from_file(temp_path)
        counts, _ = count_calls_from_file(temp_path, functions)

        call_counts = {c.function_qualified_name: c.call_count for c in counts}

        assert call_counts[make_qualified_name("__module__.xmlParser.parse")] == 1
        assert call_counts[make_qualified_name("__module__.dataProcessor.process")] == 1
        assert call_counts[make_qualified_name("__module__.dataProcessor.validate")] == 1  # Called by process


def test_nested_class_method_calls() -> None:
    """Test that nested class method calls are correctly resolved."""
    code = """
class Outer:
    class Inner:
        def process(self):
            return "processing"

    def use_inner_qualified(self):
        # Fully qualified reference
        return Outer.Inner.process(None)

    def use_inner_unqualified(self):
        # Unqualified reference - should still resolve to __module__.Outer.Inner.process
        return Inner.process(None)

def use_at_module():
    # This will be counted
    return Outer.Inner.process(None)
"""

    with temp_python_file(code) as temp_path:
        functions = parse_functions_from_file(temp_path)
        counts, _ = count_calls_from_file(temp_path, functions)

        call_counts = {c.function_qualified_name: c.call_count for c in counts}

        # All three calls to Outer.Inner.process should be counted
        assert call_counts[make_qualified_name("__module__.Outer.Inner.process")] == 3


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
        functions = parse_functions_from_file(temp_path)
        counts, _ = count_calls_from_file(temp_path, functions)

        # Since we don't track built-in methods in known_functions,
        # none of these will appear in the counts
        # But they won't cause false positives either
        call_counts = {c.function_qualified_name: c.call_count for c in counts}
        assert call_counts.get(make_qualified_name("__module__.use_builtins"), 0) == 0


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
        functions = parse_functions_from_file(temp_path)
        counts, _ = count_calls_from_file(temp_path, functions)

        call_counts = {c.function_qualified_name: c.call_count for c in counts}

        # Only LocalClass.local_method should be counted
        assert call_counts[make_qualified_name("__module__.LocalClass.local_method")] == 1
        assert call_counts.get(make_qualified_name("__module__.use_imports"), 0) == 0
        assert call_counts.get(make_qualified_name("__module__.use_local"), 0) == 0


def test_instance_method_calls_tracked() -> None:
    """Test that instance method calls via variables are tracked."""
    code = """
class Calculator:
    def add(self, a, b):
        return a + b

    def multiply(self, a, b):
        return a * b

def main():
    calc = Calculator()  # Instance creation
    result1 = calc.add(5, 7)  # Instance method call
    result2 = calc.multiply(3, 4)  # Instance method call

    # Class method calls
    result3 = Calculator.add(None, 1, 2)
    result4 = Calculator.multiply(None, 3, 4)

    return result1 + result2 + result3 + result4
"""

    with temp_python_file(code) as temp_path:
        functions = parse_functions_from_file(temp_path)
        counts, _ = count_calls_from_file(temp_path, functions)

        call_counts = {c.function_qualified_name: c.call_count for c in counts}

        # Both instance and direct class method calls should be counted
        # calc.add() + Calculator.add() = 2
        assert call_counts[make_qualified_name("__module__.Calculator.add")] == 2
        # calc.multiply() + Calculator.multiply() = 2
        assert call_counts[make_qualified_name("__module__.Calculator.multiply")] == 2


def test_forward_reference_class() -> None:
    """Test that forward-referenced classes are handled correctly."""
    code = """
def process(calc: "Calculator"):  # Forward reference
    # calc.add won't be tracked (instance method)
    return Calculator.add(None, 1, 2)  # Forward reference - can't be resolved

class Calculator:
    def add(self, a, b):
        return a + b

def use_calculator():
    return Calculator.add(None, 3, 4)  # Can be resolved - Calculator is defined
"""

    with temp_python_file(code) as temp_path:
        functions = parse_functions_from_file(temp_path)
        counts, _ = count_calls_from_file(temp_path, functions)

        call_counts = {c.function_qualified_name: c.call_count for c in counts}

        # Only the call in use_calculator is counted (position-aware resolution can't resolve
        # the forward reference in process() where Calculator.add is called before Calculator is defined)
        assert call_counts[make_qualified_name("__module__.Calculator.add")] == 1


def test_complex_scope_resolution() -> None:
    """Test complex scope resolution for nested classes."""
    code = """
class Outer:
    class Inner:
        def inner_method(self):
            return "inner"

    def use_inner_qualified(self):
        # Fully qualified reference inside Outer
        return Outer.Inner.inner_method(None)

    def use_inner_unqualified(self):
        # Unqualified reference - should resolve from Outer scope
        return Inner.inner_method(None)

    class AnotherInner:
        def another_method(self):
            # From AnotherInner, using unqualified Inner
            return Inner.inner_method(None)

        def another_method_qualified(self):
            # From AnotherInner, using qualified reference
            return Outer.Inner.inner_method(None)

def module_level_use():
    return Outer.Inner.inner_method(None)
"""

    with temp_python_file(code) as temp_path:
        functions = parse_functions_from_file(temp_path)
        counts, _ = count_calls_from_file(temp_path, functions)

        call_counts = {c.function_qualified_name: c.call_count for c in counts}

        # All five calls to Outer.Inner.inner_method should be counted
        assert call_counts[make_qualified_name("__module__.Outer.Inner.inner_method")] == 5


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
        functions = parse_functions_from_file(temp_path)
        counts, _ = count_calls_from_file(temp_path, functions)

        call_counts = {c.function_qualified_name: c.call_count for c in counts}

        # Only MyClass.method should be counted
        assert call_counts[make_qualified_name("__module__.MyClass.method")] == 1


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
        functions = parse_functions_from_file(temp_path)
        counts, _ = count_calls_from_file(temp_path, functions)

        call_counts = {c.function_qualified_name: c.call_count for c in counts}

        # Each LocalClass.local_method in its respective function scope
        assert call_counts[make_qualified_name("__module__.factory.LocalClass.local_method")] == 1
        assert call_counts[make_qualified_name("__module__.another_factory.LocalClass.local_method")] == 1


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
        result = analyze_file(str(temp_path))
        results = result.priorities

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

        assert call_counts[make_qualified_name("__module__.NetworkClient.connect")] == 1
        # Called by send_data
        assert call_counts[make_qualified_name("__module__.NetworkClient.validate")] == 1
        # Called by send_data
        assert call_counts[make_qualified_name("__module__.NetworkClient._transmit")] == 1
        assert call_counts[make_qualified_name("__module__.ErrorHandler.handle_error")] == 1
