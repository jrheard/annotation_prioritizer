"""Unit tests for the scoring module."""

from pathlib import Path

import pytest

from annotation_prioritizer.models import ParameterInfo, make_qualified_name
from annotation_prioritizer.scoring import (
    PARAMETERS_WEIGHT,
    RETURN_TYPE_WEIGHT,
    calculate_annotation_score,
    calculate_parameter_score,
    calculate_return_score,
)
from tests.helpers.factories import make_function_info, make_parameter


@pytest.mark.parametrize(
    "parameters",
    [
        (),  # No parameters
        (make_parameter("self"),),  # Only self
        (make_parameter("cls"),),  # Only cls
    ],
)
def test_implicit_parameters_get_perfect_score(parameters: tuple[ParameterInfo, ...]) -> None:
    """Functions with only implicit/no parameters get perfect parameter score."""
    score = calculate_parameter_score(parameters)
    assert score == 1.0


def test_all_parameters_annotated() -> None:
    """Functions with all parameters annotated should get perfect score."""
    parameters = (
        make_parameter("a", annotated=True),
        make_parameter("b", annotated=True),
        make_parameter("c", annotated=True),
    )
    score = calculate_parameter_score(parameters)
    assert score == 1.0


def test_no_parameters_annotated() -> None:
    """Functions with no parameters annotated should get zero score."""
    parameters = (
        make_parameter("a"),
        make_parameter("b"),
    )
    score = calculate_parameter_score(parameters)
    assert score == 0.0


def test_partial_parameters_annotated() -> None:
    """Functions with some parameters annotated should get proportional score."""
    parameters = (
        make_parameter("a", annotated=True),
        make_parameter("b"),
        make_parameter("c", annotated=True),
    )
    score = calculate_parameter_score(parameters)
    assert score == 2.0 / 3.0


def test_single_parameter_annotated() -> None:
    """Single annotated parameter should get perfect score."""
    parameters = (make_parameter("param", annotated=True),)
    score = calculate_parameter_score(parameters)
    assert score == 1.0


def test_single_parameter_not_annotated() -> None:
    """Single unannotated parameter should get zero score."""
    parameters = (make_parameter("param"),)
    score = calculate_parameter_score(parameters)
    assert score == 0.0


def test_variadic_parameters() -> None:
    """Variadic parameters (*args, **kwargs) should be treated normally."""
    parameters = (
        make_parameter("regular", annotated=True),
        make_parameter("args", variadic=True),
        make_parameter("kwargs", annotated=True, keyword=True),
    )
    score = calculate_parameter_score(parameters)
    assert score == 2.0 / 3.0


def test_annotated_return_gets_perfect_score() -> None:
    """Annotated return type should get perfect score."""
    score = calculate_return_score(has_return_annotation=True)
    assert score == 1.0


def test_unannotated_return_gets_zero_score() -> None:
    """Unannotated return type should get zero score."""
    score = calculate_return_score(has_return_annotation=False)
    assert score == 0.0


def test_fully_annotated_function() -> None:
    """Fully annotated function should get perfect total score."""
    function_info = make_function_info(
        "test_func",
        parameters=(
            make_parameter("a", annotated=True),
            make_parameter("b", annotated=True),
        ),
        has_return_annotation=True,
        line_number=10,
        file_path=Path("/test/file.py"),
    )

    score = calculate_annotation_score(function_info)

    assert score.function_qualified_name == "__module__.test_func"
    assert score.parameter_score == 1.0
    assert score.return_score == 1.0
    assert score.total_score == 1.0


def test_no_annotations_function() -> None:
    """Function with no annotations should get zero total score."""
    function_info = make_function_info(
        "test_func",
        parameters=(
            make_parameter("a"),
            make_parameter("b"),
        ),
        has_return_annotation=False,
        line_number=10,
        file_path=Path("/test/file.py"),
    )

    score = calculate_annotation_score(function_info)

    assert score.parameter_score == 0.0
    assert score.return_score == 0.0
    assert score.total_score == 0.0


def test_no_parameters_with_return_annotation() -> None:
    """Function with no parameters but return annotation should get partial score."""
    function_info = make_function_info(
        "test_func",
        has_return_annotation=True,
        line_number=10,
        file_path=Path("/test/file.py"),
    )

    score = calculate_annotation_score(function_info)

    assert score.parameter_score == 1.0
    assert score.return_score == 1.0
    assert score.total_score == 1.0


def test_no_parameters_without_return_annotation() -> None:
    """Function with no parameters and no return annotation should get partial score."""
    function_info = make_function_info(
        "test_func",
        has_return_annotation=False,
        line_number=10,
        file_path=Path("/test/file.py"),
    )

    score = calculate_annotation_score(function_info)

    assert score.parameter_score == 1.0
    assert score.return_score == 0.0
    # Total = 0.75 * 1.0 + 0.25 * 0.0 = 0.75
    assert score.total_score == PARAMETERS_WEIGHT


def test_partial_parameters_with_return_annotation() -> None:
    """Function with partial parameter annotations and return annotation."""
    function_info = make_function_info(
        "test_func",
        parameters=(
            make_parameter("a", annotated=True),
            make_parameter("b"),
        ),
        has_return_annotation=True,
        line_number=10,
        file_path=Path("/test/file.py"),
    )

    score = calculate_annotation_score(function_info)

    assert score.parameter_score == 0.5
    assert score.return_score == 1.0
    # Total = 0.75 * 0.5 + 0.25 * 1.0 = 0.375 + 0.25 = 0.625
    expected_total = PARAMETERS_WEIGHT * 0.5 + RETURN_TYPE_WEIGHT * 1.0
    assert score.total_score == expected_total


def test_partial_parameters_without_return_annotation() -> None:
    """Function with partial parameter annotations and no return annotation."""
    function_info = make_function_info(
        "test_func",
        parameters=(
            make_parameter("a", annotated=True),
            make_parameter("b"),
        ),
        has_return_annotation=False,
        line_number=10,
        file_path=Path("/test/file.py"),
    )

    score = calculate_annotation_score(function_info)

    assert score.parameter_score == 0.5
    assert score.return_score == 0.0
    # Total = 0.75 * 0.5 + 0.25 * 0.0 = 0.375
    expected_total = PARAMETERS_WEIGHT * 0.5
    assert score.total_score == expected_total


def test_weighted_scoring_constants() -> None:
    """Verify that the weight constants sum to 1.0."""
    assert PARAMETERS_WEIGHT + RETURN_TYPE_WEIGHT == 1.0


def test_complex_parameter_mix() -> None:
    """Test scoring with a complex mix of parameter types."""
    function_info = make_function_info(
        "complex_func",
        qualified_name=make_qualified_name("__module__.ClassName.complex_func"),
        parameters=(
            make_parameter("self"),
            make_parameter("a", annotated=True),
            make_parameter("args", variadic=True),
            make_parameter("kwargs", annotated=True, keyword=True),
        ),
        has_return_annotation=False,
        line_number=25,
        file_path=Path("/test/complex.py"),
    )

    score = calculate_annotation_score(function_info)

    # self is ignored, 2 out of 3 relevant parameters annotated = 2/3
    assert score.parameter_score == 2.0 / 3.0
    assert score.return_score == 0.0
    assert score.function_qualified_name == "__module__.ClassName.complex_func"
    expected_total = PARAMETERS_WEIGHT * (2.0 / 3.0)
    assert score.total_score == expected_total


def test_method_with_self_and_annotated_params() -> None:
    """Method with self + annotated params should get perfect parameter score."""
    parameters = (
        make_parameter("self"),
        make_parameter("x", annotated=True),
        make_parameter("y", annotated=True),
    )
    score = calculate_parameter_score(parameters)
    assert score == 1.0


def test_method_with_self_and_mixed_annotations() -> None:
    """Method with self + mixed annotations should score based only on real params."""
    parameters = (
        make_parameter("self"),
        make_parameter("x", annotated=True),
        make_parameter("y"),
    )
    score = calculate_parameter_score(parameters)
    # Only x and y count, 1 out of 2 annotated = 0.5
    assert score == 0.5


def test_classmethod_with_cls_and_mixed_annotations() -> None:
    """Class method with cls + mixed annotations should score based only on real params."""
    parameters = (
        make_parameter("cls"),
        make_parameter("value", annotated=True),
        make_parameter("config"),
    )
    score = calculate_parameter_score(parameters)
    # Only value and config count, 1 out of 2 annotated = 0.5
    assert score == 0.5


def test_both_self_and_cls_ignored() -> None:
    """Unusual case where both self and cls are present should ignore both."""
    parameters = (
        make_parameter("self"),
        make_parameter("cls"),
        make_parameter("x", annotated=True),
    )
    score = calculate_parameter_score(parameters)
    # Only x counts, 1 out of 1 annotated = 1.0
    assert score == 1.0
