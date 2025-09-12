"""End-to-end integration tests for the type annotation prioritizer."""

from annotation_prioritizer.analyzer import analyze_file
from tests.helpers.temp_files import temp_python_file


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
        priorities = analyze_file(path)

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
        priorities = analyze_file(path)
        assert priorities == ()


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
        priorities = analyze_file(path)

        # Should find 5 functions (4 methods + 1 function)
        assert len(priorities) == 5

        # Check qualified names include class prefix
        qualified_names = {p.function_info.qualified_name for p in priorities}
        expected_names = {
            "Calculator.add",
            "Calculator.subtract",
            "Calculator.multiply",
            "Calculator.calculate_all",
            "use_calculator",
        }
        assert qualified_names == expected_names

        # Find the method with highest priority (most calls, least annotated)
        priorities_by_name = {p.function_info.qualified_name: p for p in priorities}

        subtract = priorities_by_name["Calculator.subtract"]
        # self is ignored, x and y are unannotated, return is unannotated
        # parameter_score = 0/2, return_score = 0.0, total = 0.75 * 0 + 0.25 * 0 = 0.0
        assert subtract.annotation_score.total_score == 0.0
        assert subtract.call_count == 1

        multiply = priorities_by_name["Calculator.multiply"]
        # self is ignored, x is annotated, y is unannotated, return is annotated
        # parameter_score = 1/2, return_score = 1.0, total = 0.75 * 0.5 + 0.25 * 1.0 = 0.625
        assert multiply.annotation_score.total_score == 0.625
        assert multiply.call_count == 1

        add = priorities_by_name["Calculator.add"]
        # self is ignored, x and y are annotated, return is annotated
        # parameter_score = 2/2, return_score = 1.0, total = 0.75 * 1.0 + 0.25 * 1.0 = 1.0
        assert add.annotation_score.total_score == 1.0
        assert add.call_count == 1
