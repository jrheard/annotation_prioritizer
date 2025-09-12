"""Unit tests for the scoring module."""

import pytest

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

    @pytest.mark.parametrize(
        "parameters",
        [
            (),  # No parameters
            (ParameterInfo("self", False, False, False),),  # Only self
            (ParameterInfo("cls", False, False, False),),  # Only cls
        ],
    )
    def test_implicit_parameters_get_perfect_score(self, parameters: tuple[ParameterInfo, ...]) -> None:
        """Functions with only implicit/no parameters get perfect parameter score."""
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

        # self is ignored, 2 out of 3 relevant parameters annotated = 2/3
        assert score.parameter_score == 2.0 / 3.0
        assert score.return_score == 0.0
        assert score.function_qualified_name == "module.ClassName.complex_func"
        expected_total = PARAMETERS_WEIGHT * (2.0 / 3.0)
        assert score.total_score == expected_total

    def test_method_with_self_and_annotated_params(self) -> None:
        """Method with self + annotated params should get perfect parameter score."""
        parameters = (
            ParameterInfo("self", has_annotation=False, is_variadic=False, is_keyword=False),
            ParameterInfo("x", has_annotation=True, is_variadic=False, is_keyword=False),
            ParameterInfo("y", has_annotation=True, is_variadic=False, is_keyword=False),
        )
        score = calculate_parameter_score(parameters)
        assert score == 1.0

    def test_method_with_self_and_mixed_annotations(self) -> None:
        """Method with self + mixed annotations should score based only on real params."""
        parameters = (
            ParameterInfo("self", has_annotation=False, is_variadic=False, is_keyword=False),
            ParameterInfo("x", has_annotation=True, is_variadic=False, is_keyword=False),
            ParameterInfo("y", has_annotation=False, is_variadic=False, is_keyword=False),
        )
        score = calculate_parameter_score(parameters)
        # Only x and y count, 1 out of 2 annotated = 0.5
        assert score == 0.5

    def test_classmethod_with_cls_and_mixed_annotations(self) -> None:
        """Class method with cls + mixed annotations should score based only on real params."""
        parameters = (
            ParameterInfo("cls", has_annotation=False, is_variadic=False, is_keyword=False),
            ParameterInfo("value", has_annotation=True, is_variadic=False, is_keyword=False),
            ParameterInfo("config", has_annotation=False, is_variadic=False, is_keyword=False),
        )
        score = calculate_parameter_score(parameters)
        # Only value and config count, 1 out of 2 annotated = 0.5
        assert score == 0.5

    def test_both_self_and_cls_ignored(self) -> None:
        """Unusual case where both self and cls are present should ignore both."""
        parameters = (
            ParameterInfo("self", has_annotation=False, is_variadic=False, is_keyword=False),
            ParameterInfo("cls", has_annotation=False, is_variadic=False, is_keyword=False),
            ParameterInfo("x", has_annotation=True, is_variadic=False, is_keyword=False),
        )
        score = calculate_parameter_score(parameters)
        # Only x counts, 1 out of 1 annotated = 1.0
        assert score == 1.0
