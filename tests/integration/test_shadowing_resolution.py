"""Integration tests for position-aware shadowing resolution (issue #31).

These tests verify that position-aware resolution correctly handles Python's
name shadowing semantics, where later definitions shadow earlier ones.
"""

from annotation_prioritizer.models import make_qualified_name
from tests.helpers.factories import make_function_info, make_parameter
from tests.helpers.function_parsing import count_calls_from_file
from tests.helpers.temp_files import temp_python_file


def test_import_shadowed_by_local_function() -> None:
    """Test that local function definition shadows earlier import."""
    code = """
from math import sqrt

# First call - should be unresolvable (imported)
result1 = sqrt(4)

# Define local sqrt that shadows the import
def sqrt(x):
    return x ** 0.5

# Second call - should resolve to local sqrt
result2 = sqrt(9)
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            make_function_info(
                "sqrt",
                qualified_name=make_qualified_name("__module__.sqrt"),
                parameters=(make_parameter("x"),),
                line_number=8,
                file_path=temp_path,
            ),
        )

        result, unresolvable_calls = count_calls_from_file(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # Second call resolves to local sqrt (line 12, after definition at line 8)
        assert call_counts[make_qualified_name("__module__.sqrt")] == 1

        # First call is unresolvable (line 5, before local definition, refers to import)
        assert len(unresolvable_calls) == 1
        assert "sqrt(4)" in unresolvable_calls[0].call_text


def test_class_shadowed_by_local_class() -> None:
    """Test that local class definition shadows earlier class."""
    code = """
class Calculator:
    def add(self, a, b):
        return a + b

# First call - should resolve to first Calculator
calc1 = Calculator()
result1 = calc1.add(1, 2)

# Shadow with new Calculator class
class Calculator:
    def add(self, a, b):
        return a + b + 100

# Second call - should resolve to second Calculator
calc2 = Calculator()
result2 = calc2.add(3, 4)
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

        # Both calls resolve to the first Calculator.add (only one Calculator in known_functions)
        # The second Calculator is a different class but has the same qualified name,
        # so both variable assignments resolve to the first one
        assert call_counts[make_qualified_name("__module__.Calculator.add")] == 2


def test_multiple_function_shadows_in_same_scope() -> None:
    """Test multiple redefinitions of the same function name."""
    code = """
def process(x):
    return x + 1

result1 = process(10)  # First definition

def process(x):
    return x + 2

result2 = process(20)  # Second definition

def process(x):
    return x + 3

result3 = process(30)  # Third definition
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            make_function_info(
                "process",
                qualified_name=make_qualified_name("__module__.process"),
                parameters=(make_parameter("x"),),
                line_number=2,
                file_path=temp_path,
            ),
        )

        result, _ = count_calls_from_file(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # All three calls resolve (each to the most recent definition before the call)
        assert call_counts[make_qualified_name("__module__.process")] == 3


def test_shadowing_in_nested_scopes() -> None:
    """Test that shadowing works correctly in nested scopes."""
    code = """
def outer_func():
    return "outer"

def container():
    # Call to outer scope function
    result1 = outer_func()

    # Shadow with local function
    def outer_func():
        return "inner"

    # Call to shadowing function
    result2 = outer_func()

    return result1 + result2
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            make_function_info(
                "outer_func",
                qualified_name=make_qualified_name("__module__.outer_func"),
                line_number=2,
                file_path=temp_path,
            ),
            make_function_info(
                "outer_func",
                qualified_name=make_qualified_name("__module__.container.outer_func"),
                line_number=9,
                file_path=temp_path,
            ),
        )

        result, _ = count_calls_from_file(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # First call resolves to module-level outer_func
        assert call_counts[make_qualified_name("__module__.outer_func")] == 1

        # Second call resolves to nested outer_func
        assert call_counts[make_qualified_name("__module__.container.outer_func")] == 1


def test_variable_reassignment_position_aware() -> None:
    """Test that variable reassignments are tracked position-aware."""
    code = """
class TypeA:
    def method(self):
        return "A"

class TypeB:
    def method(self):
        return "B"

def test_reassignment():
    obj = TypeA()
    result1 = obj.method()  # Should resolve to TypeA.method

    obj = TypeB()
    result2 = obj.method()  # Should resolve to TypeB.method

    return result1 + result2
"""

    with temp_python_file(code) as temp_path:
        known_functions = (
            make_function_info(
                "method",
                qualified_name=make_qualified_name("__module__.TypeA.method"),
                parameters=(make_parameter("self"),),
                line_number=3,
                file_path=temp_path,
            ),
            make_function_info(
                "method",
                qualified_name=make_qualified_name("__module__.TypeB.method"),
                parameters=(make_parameter("self"),),
                line_number=7,
                file_path=temp_path,
            ),
        )

        result, _ = count_calls_from_file(temp_path, known_functions)
        call_counts = {call.function_qualified_name: call.call_count for call in result}

        # First call resolves to TypeA.method
        assert call_counts[make_qualified_name("__module__.TypeA.method")] == 1

        # Second call resolves to TypeB.method
        assert call_counts[make_qualified_name("__module__.TypeB.method")] == 1


def test_import_not_shadowed_when_no_local_definition() -> None:
    """Test that imports remain unresolvable when not shadowed."""
    code = """
from math import sqrt, cos

# These should all be unresolvable (imported, no local shadow)
result1 = sqrt(4)
result2 = cos(0)
result3 = sqrt(16)
"""

    with temp_python_file(code) as temp_path:
        # No known functions defined locally
        _, unresolvable_calls = count_calls_from_file(temp_path, ())

        # All calls are unresolvable
        assert len(unresolvable_calls) == 3
        unresolvable_texts = [call.call_text for call in unresolvable_calls]
        assert any("sqrt(4)" in text for text in unresolvable_texts)
        assert any("cos(0)" in text for text in unresolvable_texts)
        assert any("sqrt(16)" in text for text in unresolvable_texts)


def test_cls_outside_class_context() -> None:
    """Test that cls.method() outside class context is unresolvable."""
    code = """
def free_function():
    # Invalid Python but test our handling
    cls.method()
"""

    with temp_python_file(code) as temp_path:
        _, unresolvable_calls = count_calls_from_file(temp_path, ())

        # cls.method() should be unresolvable (cls outside class)
        assert len(unresolvable_calls) == 1
        assert "cls.method()" in unresolvable_calls[0].call_text


def test_compound_class_reference_not_in_known_classes() -> None:
    """Test compound class reference that doesn't exist."""
    code = """
class Outer:
    pass

def test_call():
    # Try to call a method on Outer.NonExistent (doesn't exist)
    Outer.NonExistent.method()
"""

    with temp_python_file(code) as temp_path:
        _, unresolvable_calls = count_calls_from_file(temp_path, ())

        # Outer.NonExistent.method() should be unresolvable
        assert len(unresolvable_calls) == 1
        assert "Outer.NonExistent.method()" in unresolvable_calls[0].call_text
