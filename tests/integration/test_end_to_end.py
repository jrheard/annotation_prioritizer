"""End-to-end integration tests for the type annotation prioritizer."""

from annotation_prioritizer.analyzer import analyze_file
from annotation_prioritizer.models import make_qualified_name
from tests.helpers.temp_files import temp_python_file


def test_unresolvable_calls_tracking() -> None:
    """Test that unresolvable calls are properly tracked and categorized."""
    test_code = '''import json

class DataProcessor:
    def process_data(self, data):
        """Process data."""
        return data

def utility_function(value):
    """Utility function."""
    return value * 2

def main():
    """Function with various types of calls."""
    # Resolvable calls
    utility_function("hello")  # Direct function call - resolvable

    # Resolvable calls
    processor = DataProcessor()
    processor.process_data("test")  # Instance method - resolvable

    # Unresolvable calls
    getattr(processor, 'process_data')("dynamic")  # getattr - unresolvable

    handlers = {'process': processor.process_data}
    handlers['process']("subscript")  # Subscript - unresolvable

    json.dumps({'key': 'value'})  # Imported module - unresolvable

    eval("utility_function('eval')")  # eval - unresolvable
'''

    with temp_python_file(test_code) as path:
        result = analyze_file(str(path))

        # Check that we have functions (including synthetic __init__)
        assert (
            len(result.priorities) == 4
        )  # DataProcessor.__init__ (synthetic), DataProcessor.process_data, utility_function, main

        # Check call counts
        priorities_by_name = {p.function_info.qualified_name: p for p in result.priorities}
        utility = priorities_by_name[make_qualified_name("__module__.utility_function")]
        assert utility.call_count == 1  # Direct call is counted

        # processor.process_data is resolvable
        processor_method = priorities_by_name[make_qualified_name("__module__.DataProcessor.process_data")]
        assert processor_method.call_count == 1  # Instance method call is tracked

        # Check unresolvable calls
        assert len(result.unresolvable_calls) > 0

        # Check that various types of unresolvable calls were found
        call_texts = [call.call_text for call in result.unresolvable_calls]

        # We should have captured different kinds of unresolvable calls
        assert any("getattr" in text for text in call_texts)  # getattr call
        assert any("handlers" in text for text in call_texts)  # Subscript call
        # eval is a built-in function and not reported as unresolvable
        assert any("json.dumps" in text for text in call_texts)  # Imported function


def test_complex_qualified_calls() -> None:
    """Test that deeply nested attribute chains are tracked as unresolvable."""
    test_code = """class App:
    class Services:
        class Database:
            class Connection:
                def execute(self, query):
                    return query

def test():
    # This deeply nested call should be unresolvable
    app.services.database.connection.execute("SELECT * FROM users")
"""

    with temp_python_file(test_code) as path:
        result = analyze_file(str(path))

        # Should have unresolvable calls
        assert len(result.unresolvable_calls) > 0

        # Find the complex qualified call
        complex_calls = [c for c in result.unresolvable_calls if "execute" in c.call_text]
        assert len(complex_calls) >= 1
        assert "app.services.database.connection.execute" in complex_calls[0].call_text


def test_analyze_simple_file() -> None:
    """Test analyzing a simple Python file with mixed annotations."""
    test_code = '''def unannotated_function(x, y):
    """Function with no annotations."""
    return x + y

def partially_annotated_function(x: int, y) -> int:
    """Function with partial annotations."""
    return x + y

def fully_annotated_function(x: int, y: int) -> int:
    """Function with full annotations."""
    return x + y

def caller():
    """Function that calls others."""
    result1 = unannotated_function(1, 2)  # Called once
    result2 = partially_annotated_function(3, 4)  # Called once
    result3 = fully_annotated_function(5, 6)  # Called once

    # Call unannotated function multiple times
    for i in range(5):
        unannotated_function(i, i+1)

    return result1 + result2 + result3
'''

    with temp_python_file(test_code) as path:
        result = analyze_file(str(path))
        priorities = result.priorities

        # Should find 4 functions
        assert len(priorities) == 4

        # Sort by function name for predictable testing
        priorities_by_name = {p.function_info.name: p for p in priorities}

        # Check that all functions are found
        expected_functions = {
            "unannotated_function",
            "partially_annotated_function",
            "fully_annotated_function",
            "caller",
        }
        assert set(priorities_by_name.keys()) == expected_functions

        # Check annotation scores
        unannotated = priorities_by_name["unannotated_function"]
        assert unannotated.annotation_score.parameter_score == 0.0  # No param annotations
        assert unannotated.annotation_score.return_score == 0.0  # No return annotation
        assert unannotated.annotation_score.total_score == 0.0  # Completely unannotated

        partially = priorities_by_name["partially_annotated_function"]
        assert partially.annotation_score.parameter_score == 0.5  # 1 of 2 params annotated
        assert partially.annotation_score.return_score == 1.0  # Return annotated
        assert partially.annotation_score.total_score == 0.625  # 0.75 * 0.5 + 0.25 * 1.0

        fully = priorities_by_name["fully_annotated_function"]
        assert fully.annotation_score.parameter_score == 1.0  # All params annotated
        assert fully.annotation_score.return_score == 1.0  # Return annotated
        assert fully.annotation_score.total_score == 1.0  # Fully annotated

        caller_func = priorities_by_name["caller"]
        assert caller_func.annotation_score.parameter_score == 1.0  # No params = 100%
        assert caller_func.annotation_score.return_score == 0.0  # No return annotation
        assert caller_func.annotation_score.total_score == 0.75  # 0.75 * 1.0 + 0.25 * 0.0

        # Check call counts (static analysis counts call sites, not runtime calls)
        assert unannotated.call_count == 2  # Called at 2 different locations
        assert partially.call_count == 1  # Called once
        assert fully.call_count == 1  # Called once
        assert caller_func.call_count == 0  # Not called by any other function

        # Check priority scores (highest priority = more calls * less annotated)
        assert unannotated.priority_score == 2.0  # 2 calls * (1.0 - 0.0)
        assert partially.priority_score == 0.375  # 1 call * (1.0 - 0.625)
        assert fully.priority_score == 0.0  # 1 call * (1.0 - 1.0)
        assert caller_func.priority_score == 0.0  # 0 calls * (1.0 - 0.75)

        # Check that results are sorted by priority (highest first)
        priority_scores = [p.priority_score for p in priorities]
        assert priority_scores == sorted(priority_scores, reverse=True)

        # unannotated_function should be first (highest priority)
        assert priorities[0].function_info.name == "unannotated_function"


def test_analyze_empty_file() -> None:
    """Test analyzing an empty Python file."""
    with temp_python_file("# Empty file\n") as path:
        result = analyze_file(str(path))
        priorities = result.priorities
        assert priorities == ()


def test_analyze_nonexistent_file() -> None:
    """Test analyzing a nonexistent file returns empty result."""
    result = analyze_file("/nonexistent/file.py")
    assert result.priorities == ()
    assert result.unresolvable_calls == ()


def test_variable_tracking_comprehensive() -> None:
    """Test comprehensive variable tracking scenarios for instance method resolution."""
    test_code = '''class Calculator:
    def add(self, x: int, y: int) -> int:
        """Add two numbers."""
        return x + y

    def multiply(self, x: int, y: int) -> int:
        """Multiply two numbers."""
        return x * y

class Helper:
    def add(self, a: int, b: int) -> int:
        """Add two numbers with different params."""
        return a + b

    def assist(self) -> str:
        """Provide assistance."""
        return "helping"

# Module-level variable tracking
module_calc = Calculator()
module_result = module_calc.add(1, 2)  # Should be tracked

def use_direct_instantiation():
    """Test direct instantiation tracking."""
    calc = Calculator()
    return calc.add(5, 6)  # Should be tracked

def use_parameter_annotation(calc: Calculator):
    """Test parameter type annotation tracking."""
    return calc.multiply(3, 4)  # Should be tracked

def use_variable_annotation():
    """Test variable type annotation tracking."""
    calc: Calculator = Calculator()
    return calc.add(7, 8)  # Should be tracked

def use_reassignment():
    """Test variable reassignment - uses final type for all references."""
    obj = Calculator()
    result1 = obj.add(1, 2)  # Will be attributed to Helper.add due to two-pass limitation
    obj = Helper()
    result2 = obj.add(3, 4)  # Will be attributed to Helper.add
    return result1 + result2

def use_nested_scope():
    """Test parent scope variable access in nested functions."""
    calc = Calculator()

    def inner():
        # Access parent scope variable
        return calc.multiply(2, 3)  # Should be tracked

    return inner()

def use_class_reference():
    """Test class reference vs instance."""
    CalcClass = Calculator  # Class reference, not instance
    calc = CalcClass()  # Now it's an instance
    return calc.add(9, 10)  # Should be tracked

def mixed_patterns():
    """Test multiple patterns together."""
    # Direct instantiation
    c1 = Calculator()
    r1 = c1.add(1, 1)

    # Variable annotation
    c2: Helper = Helper()
    r2 = c2.assist()

    # Nested function with parent scope
    def nested():
        return c1.multiply(2, 2) + len(c2.assist())

    return r1 + nested()
'''

    with temp_python_file(test_code) as path:
        result = analyze_file(str(path))

        # Get priorities indexed by qualified name
        priorities_by_name = {p.function_info.qualified_name: p for p in result.priorities}

        # Test that Calculator.add is tracked from multiple sources
        calc_add = priorities_by_name.get(make_qualified_name("__module__.Calculator.add"))
        assert calc_add is not None
        # Should be called from: module level, use_direct_instantiation,
        # use_variable_annotation, mixed_patterns
        # Note: use_reassignment calls are attributed to Helper.add due to two-pass limitation
        # Note: use_class_reference's CalcClass() is not tracked (class reference assignment not supported)
        assert calc_add.call_count == 4

        # Test that Calculator.multiply is tracked from parameter annotations and nested scope
        calc_multiply = priorities_by_name.get(make_qualified_name("__module__.Calculator.multiply"))
        assert calc_multiply is not None
        # Should be called from: use_parameter_annotation, use_nested_scope, mixed_patterns
        assert calc_multiply.call_count == 3

        # Test that Helper.add is tracked (including reassignment calls)
        helper_add = priorities_by_name.get(make_qualified_name("__module__.Helper.add"))
        assert helper_add is not None
        # Gets both calls from use_reassignment due to two-pass limitation
        assert helper_add.call_count == 2

        # Test that Helper.assist is tracked
        helper_assist = priorities_by_name.get(make_qualified_name("__module__.Helper.assist"))
        assert helper_assist is not None
        assert helper_assist.call_count == 2  # Called in mixed_patterns twice

        # Verify that most variable-based calls are resolvable
        unresolvable_texts = [call.call_text for call in result.unresolvable_calls]

        # Most calc.add and calc.multiply calls should be resolved
        # Exception: use_class_reference's calc.add(9, 10) is unresolvable
        # because CalcClass() instantiation is not tracked (class reference assignment not supported)
        calc_add_unresolved = [t for t in unresolvable_texts if "calc.add" in t]
        assert len(calc_add_unresolved) <= 1  # Only use_class_reference's call

        # No calc.multiply should be unresolvable
        assert not any("calc.multiply" in text for text in unresolvable_texts)

        # No obj.add should be unresolvable (they're attributed to Helper.add)
        assert not any("obj.add" in text for text in unresolvable_texts)

        # Module-level calls should be tracked
        assert not any("module_calc.add" in text for text in unresolvable_texts)

        # Constructor calls are tracked as __init__ calls
        assert not any("Calculator()" in text for text in unresolvable_texts)
        # Built-in functions like len() are not reported as unresolvable


def test_analyze_file_with_classes() -> None:
    """Test analyzing a file with class methods."""
    test_code = '''class Calculator:
    def add(self, x: int, y: int) -> int:
        """Fully annotated method."""
        return x + y

    def subtract(self, x, y):
        """Unannotated method."""
        return x - y

    def multiply(self, x: int, y) -> int:
        """Partially annotated method."""
        return x * y

    def calculate_all(self):
        """Method that calls others."""
        a = self.add(5, 3)
        b = self.subtract(10, 4)
        c = self.multiply(2, 6)
        return a + b + c

def use_calculator():
    """Function using the calculator."""
    calc = Calculator()
    return calc.calculate_all()
'''

    with temp_python_file(test_code) as path:
        result = analyze_file(str(path))
        priorities = result.priorities

        # Should find 6 functions (4 methods + 1 synthetic __init__ + 1 function)
        assert len(priorities) == 6

        # Check qualified names include class prefix (including synthetic __init__)
        qualified_names = {p.function_info.qualified_name for p in priorities}
        expected_names = {
            "__module__.Calculator.add",
            "__module__.Calculator.subtract",
            "__module__.Calculator.multiply",
            "__module__.Calculator.calculate_all",
            "__module__.use_calculator",
            "__module__.Calculator.__init__",  # Synthetic
        }
        assert qualified_names == expected_names

        # Find the method with highest priority (most calls, least annotated)
        priorities_by_name = {p.function_info.qualified_name: p for p in priorities}

        subtract = priorities_by_name[make_qualified_name("__module__.Calculator.subtract")]
        # self is ignored, x and y are unannotated, return is unannotated
        # parameter_score = 0/2, return_score = 0.0, total = 0.75 * 0 + 0.25 * 0 = 0.0
        assert subtract.annotation_score.total_score == 0.0
        assert subtract.call_count == 1

        multiply = priorities_by_name[make_qualified_name("__module__.Calculator.multiply")]
        # self is ignored, x is annotated, y is unannotated, return is annotated
        # parameter_score = 1/2, return_score = 1.0, total = 0.75 * 0.5 + 0.25 * 1.0 = 0.625
        assert multiply.annotation_score.total_score == 0.625
        assert multiply.call_count == 1

        add = priorities_by_name[make_qualified_name("__module__.Calculator.add")]
        # self is ignored, x and y are annotated, return is annotated
        # parameter_score = 2/2, return_score = 1.0, total = 0.75 * 1.0 + 0.25 * 1.0 = 1.0
        assert add.annotation_score.total_score == 1.0
        assert add.call_count == 1
