"""Unit tests for the scoring module."""

from annotation_prioritizer.models import FunctionInfo, ParameterInfo
from annotation_prioritizer.scoring import (
    PARAMETERS_WEIGHT,
    RETURN_TYPE_WEIGHT,
    calculate_annotation_score,
    calculate_parameter_score,
    calculate_return_score,
)


class TestCalculateParameterScore:
    """Tests for calculate_parameter_score function."""

    def test_no_parameters_returns_perfect_score(self) -> None:
        """Functions with no parameters should get a perfect parameter score."""
        parameters = ()
        score = calculate_parameter_score(parameters)
        assert score == 1.0

    def test_all_parameters_annotated(self) -> None:
        """Functions with all parameters annotated should get perfect score."""
        parameters = (
            ParameterInfo("a", has_annotation=True, is_variadic=False, is_keyword=False),
            ParameterInfo("b", has_annotation=True, is_variadic=False, is_keyword=False),
            ParameterInfo("c", has_annotation=True, is_variadic=False, is_keyword=False),
        )
        score = calculate_parameter_score(parameters)
        assert score == 1.0

    def test_no_parameters_annotated(self) -> None:
        """Functions with no parameters annotated should get zero score."""
        parameters = (
            ParameterInfo("a", has_annotation=False, is_variadic=False, is_keyword=False),
            ParameterInfo("b", has_annotation=False, is_variadic=False, is_keyword=False),
        )
        score = calculate_parameter_score(parameters)
        assert score == 0.0

    def test_partial_parameters_annotated(self) -> None:
        """Functions with some parameters annotated should get proportional score."""
        parameters = (
            ParameterInfo("a", has_annotation=True, is_variadic=False, is_keyword=False),
            ParameterInfo("b", has_annotation=False, is_variadic=False, is_keyword=False),
            ParameterInfo("c", has_annotation=True, is_variadic=False, is_keyword=False),
        )
        score = calculate_parameter_score(parameters)
        assert score == 2.0 / 3.0

    def test_single_parameter_annotated(self) -> None:
        """Single annotated parameter should get perfect score."""
        parameters = (ParameterInfo("param", has_annotation=True, is_variadic=False, is_keyword=False),)
        score = calculate_parameter_score(parameters)
        assert score == 1.0

    def test_single_parameter_not_annotated(self) -> None:
        """Single unannotated parameter should get zero score."""
        parameters = (ParameterInfo("param", has_annotation=False, is_variadic=False, is_keyword=False),)
        score = calculate_parameter_score(parameters)
        assert score == 0.0

    def test_variadic_parameters(self) -> None:
        """Variadic parameters (*args, **kwargs) should be treated normally."""
        parameters = (
            ParameterInfo("regular", has_annotation=True, is_variadic=False, is_keyword=False),
            ParameterInfo("args", has_annotation=False, is_variadic=True, is_keyword=False),
            ParameterInfo("kwargs", has_annotation=True, is_variadic=False, is_keyword=True),
        )
        score = calculate_parameter_score(parameters)
        assert score == 2.0 / 3.0


class TestCalculateReturnScore:
    """Tests for calculate_return_score function."""

    def test_annotated_return_gets_perfect_score(self) -> None:
        """Annotated return type should get perfect score."""
        score = calculate_return_score(has_return_annotation=True)
        assert score == 1.0

    def test_unannotated_return_gets_zero_score(self) -> None:
        """Unannotated return type should get zero score."""
        score = calculate_return_score(has_return_annotation=False)
        assert score == 0.0


class TestCalculateAnnotationScore:
    """Tests for calculate_annotation_score function."""

    def test_fully_annotated_function(self) -> None:
        """Fully annotated function should get perfect total score."""
        function_info = FunctionInfo(
            name="test_func",
            qualified_name="module.test_func",
            parameters=(
                ParameterInfo("a", has_annotation=True, is_variadic=False, is_keyword=False),
                ParameterInfo("b", has_annotation=True, is_variadic=False, is_keyword=False),
            ),
            has_return_annotation=True,
            line_number=10,
            file_path="/test/file.py",
        )

        score = calculate_annotation_score(function_info)

        assert score.function_qualified_name == "module.test_func"
        assert score.parameter_score == 1.0
        assert score.return_score == 1.0
        assert score.total_score == 1.0

    def test_no_annotations_function(self) -> None:
        """Function with no annotations should get zero total score."""
        function_info = FunctionInfo(
            name="test_func",
            qualified_name="module.test_func",
            parameters=(
                ParameterInfo("a", has_annotation=False, is_variadic=False, is_keyword=False),
                ParameterInfo("b", has_annotation=False, is_variadic=False, is_keyword=False),
            ),
            has_return_annotation=False,
            line_number=10,
            file_path="/test/file.py",
        )

        score = calculate_annotation_score(function_info)

        assert score.parameter_score == 0.0
        assert score.return_score == 0.0
        assert score.total_score == 0.0

    def test_no_parameters_with_return_annotation(self) -> None:
        """Function with no parameters but return annotation should get partial score."""
        function_info = FunctionInfo(
            name="test_func",
            qualified_name="module.test_func",
            parameters=(),
            has_return_annotation=True,
            line_number=10,
            file_path="/test/file.py",
        )

        score = calculate_annotation_score(function_info)

        assert score.parameter_score == 1.0
        assert score.return_score == 1.0
        assert score.total_score == 1.0

    def test_no_parameters_without_return_annotation(self) -> None:
        """Function with no parameters and no return annotation should get partial score."""
        function_info = FunctionInfo(
            name="test_func",
            qualified_name="module.test_func",
            parameters=(),
            has_return_annotation=False,
            line_number=10,
            file_path="/test/file.py",
        )

        score = calculate_annotation_score(function_info)

        assert score.parameter_score == 1.0
        assert score.return_score == 0.0
        # Total = 0.75 * 1.0 + 0.25 * 0.0 = 0.75
        assert score.total_score == PARAMETERS_WEIGHT

    def test_partial_parameters_with_return_annotation(self) -> None:
        """Function with partial parameter annotations and return annotation."""
        function_info = FunctionInfo(
            name="test_func",
            qualified_name="module.test_func",
            parameters=(
                ParameterInfo("a", has_annotation=True, is_variadic=False, is_keyword=False),
                ParameterInfo("b", has_annotation=False, is_variadic=False, is_keyword=False),
            ),
            has_return_annotation=True,
            line_number=10,
            file_path="/test/file.py",
        )

        score = calculate_annotation_score(function_info)

        assert score.parameter_score == 0.5
        assert score.return_score == 1.0
        # Total = 0.75 * 0.5 + 0.25 * 1.0 = 0.375 + 0.25 = 0.625
        expected_total = PARAMETERS_WEIGHT * 0.5 + RETURN_TYPE_WEIGHT * 1.0
        assert score.total_score == expected_total

    def test_partial_parameters_without_return_annotation(self) -> None:
        """Function with partial parameter annotations and no return annotation."""
        function_info = FunctionInfo(
            name="test_func",
            qualified_name="module.test_func",
            parameters=(
                ParameterInfo("a", has_annotation=True, is_variadic=False, is_keyword=False),
                ParameterInfo("b", has_annotation=False, is_variadic=False, is_keyword=False),
            ),
            has_return_annotation=False,
            line_number=10,
            file_path="/test/file.py",
        )

        score = calculate_annotation_score(function_info)

        assert score.parameter_score == 0.5
        assert score.return_score == 0.0
        # Total = 0.75 * 0.5 + 0.25 * 0.0 = 0.375
        expected_total = PARAMETERS_WEIGHT * 0.5
        assert score.total_score == expected_total

    def test_weighted_scoring_constants(self) -> None:
        """Verify that the weight constants sum to 1.0."""
        assert PARAMETERS_WEIGHT + RETURN_TYPE_WEIGHT == 1.0

    def test_complex_parameter_mix(self) -> None:
        """Test scoring with a complex mix of parameter types."""
        function_info = FunctionInfo(
            name="complex_func",
            qualified_name="module.ClassName.complex_func",
            parameters=(
                ParameterInfo("self", has_annotation=False, is_variadic=False, is_keyword=False),
                ParameterInfo("a", has_annotation=True, is_variadic=False, is_keyword=False),
                ParameterInfo("args", has_annotation=False, is_variadic=True, is_keyword=False),
                ParameterInfo("kwargs", has_annotation=True, is_variadic=False, is_keyword=True),
            ),
            has_return_annotation=False,
            line_number=25,
            file_path="/test/complex.py",
        )

        score = calculate_annotation_score(function_info)

        # 2 out of 4 parameters annotated = 0.5
        assert score.parameter_score == 0.5
        assert score.return_score == 0.0
        assert score.function_qualified_name == "module.ClassName.complex_func"
        expected_total = PARAMETERS_WEIGHT * 0.5
        assert score.total_score == expected_total
