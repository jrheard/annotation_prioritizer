"""Unit tests for analyzer module."""

from annotation_prioritizer.analyzer import analyze_source


def test_analyze_source_with_syntax_error() -> None:
    """Test analyze_source with invalid Python code."""
    invalid_code = """
def broken_function(
    # Missing closing parenthesis
"""
    result = analyze_source(invalid_code)

    # Should return empty result for syntax errors
    assert result.priorities == ()
    assert result.unresolvable_calls == ()


def test_analyze_source_with_valid_code() -> None:
    """Test analyze_source with valid Python code."""
    valid_code = """
def simple_function():
    pass
"""
    result = analyze_source(valid_code)

    # Should have one function
    assert len(result.priorities) == 1
    assert result.priorities[0].function_info.name == "simple_function"
