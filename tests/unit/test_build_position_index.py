"""Tests for build_position_index() factory function.

This module tests the factory function that builds a PositionIndex from
collected name bindings, including position-aware variable resolution.

TODO: Merge this file into test_position_index.py
"""

from annotation_prioritizer.models import make_qualified_name
from annotation_prioritizer.position_index import build_position_index, resolve_name
from tests.helpers.factories import (
    make_class_binding,
    make_function_binding,
    make_function_scope,
    make_import_binding,
    make_module_scope,
    make_variable_binding,
)


def test_build_index_with_no_bindings() -> None:
    """Empty bindings list should create empty index."""
    index = build_position_index([])

    # Should resolve to None for any name
    result = resolve_name(index, "foo", 10, make_module_scope())
    assert result is None


def test_build_index_with_single_binding() -> None:
    """Index with single binding should be resolvable."""
    binding = make_import_binding("sqrt", "math")
    index = build_position_index([binding])

    # Should resolve sqrt after line 1
    result = resolve_name(index, "sqrt", 10, make_module_scope())
    assert result == binding

    # Should not resolve before line 1
    result = resolve_name(index, "sqrt", 1, make_module_scope())
    assert result is None


def test_build_index_sorts_bindings_by_line_number() -> None:
    """Bindings should be sorted by line number for correct resolution."""
    # Create bindings out of order
    binding2 = make_function_binding("foo", line_number=20)
    binding1 = make_import_binding("foo", "bar", line_number=10)

    # Build index with out-of-order bindings
    index = build_position_index([binding2, binding1])

    # At line 15, should resolve to the import (line 10)
    result = resolve_name(index, "foo", 15, make_module_scope())
    assert result == binding1

    # At line 25, should resolve to the function (line 20)
    result = resolve_name(index, "foo", 25, make_module_scope())
    assert result == binding2


def test_build_index_resolves_variable_to_class() -> None:
    """Variables referencing classes should have target_class resolved."""
    class_binding = make_class_binding("Calculator")
    var_binding = make_variable_binding("calc", line_number=10)

    # Build index with unresolved variable
    index = build_position_index([class_binding, var_binding], [(var_binding, "Calculator")])

    # The variable should now have target_class resolved
    result = resolve_name(index, "calc", 15, make_module_scope())
    assert result is not None
    assert result.target_class == make_qualified_name("__module__.Calculator")


def test_build_index_variable_resolves_to_shadowed_class() -> None:
    """Variable resolution should respect shadowing (issue #31)."""
    # Import Calculator from module
    import_binding = make_import_binding("Calculator", "external")

    # Local Calculator class shadows the import
    class_binding = make_class_binding("Calculator", line_number=10)

    # Variable created after the local class
    var_binding = make_variable_binding("calc", line_number=20)

    index = build_position_index([import_binding, class_binding, var_binding], [(var_binding, "Calculator")])

    # Variable should resolve to the LOCAL class, not the import
    result = resolve_name(index, "calc", 25, make_module_scope())
    assert result is not None
    assert result.target_class == make_qualified_name("__module__.Calculator")


def test_build_index_unresolvable_variable_keeps_none() -> None:
    """Variables that can't be resolved should keep target_class=None."""
    var_binding = make_variable_binding("calc", line_number=10)

    # Try to resolve to a class that doesn't exist
    index = build_position_index([var_binding], [(var_binding, "NonexistentClass")])

    result = resolve_name(index, "calc", 15, make_module_scope())
    assert result is not None
    assert result.target_class is None


def test_build_index_variable_wont_resolve_to_function() -> None:
    """Variables referencing functions should not get target_class set."""
    func_binding = make_function_binding("process")
    var_binding = make_variable_binding("p", line_number=10)

    # Variable references a function, not a class
    index = build_position_index([func_binding, var_binding], [(var_binding, "process")])

    result = resolve_name(index, "p", 15, make_module_scope())
    assert result is not None
    assert result.target_class is None  # Should not resolve to function


def test_build_index_variable_wont_resolve_to_import() -> None:
    """Variables referencing imports should not get target_class set."""
    import_binding = make_import_binding("math", "math")
    var_binding = make_variable_binding("m", line_number=10)

    # Variable references an import, not a class
    index = build_position_index([import_binding, var_binding], [(var_binding, "math")])

    result = resolve_name(index, "m", 15, make_module_scope())
    assert result is not None
    assert result.target_class is None  # Should not resolve to import


def test_build_index_shadowing_import_by_function() -> None:
    """Import shadowed by function (issue #31 scenario)."""
    # Import: from math import sqrt
    import_binding = make_import_binding("sqrt", "math")

    # Function: def sqrt(): ...
    func_binding = make_function_binding("sqrt", line_number=10)

    index = build_position_index([import_binding, func_binding])

    # Before function definition: should resolve to import
    result = resolve_name(index, "sqrt", 5, make_module_scope())
    assert result == import_binding

    # After function definition: should resolve to function
    result = resolve_name(index, "sqrt", 15, make_module_scope())
    assert result == func_binding


def test_build_index_shadowing_function_by_import() -> None:
    """Function shadowed by later import (issue #31 scenario)."""
    # Function: def sqrt(): ...
    func_binding = make_function_binding("sqrt")

    # Import: from math import sqrt
    import_binding = make_import_binding("sqrt", "math", line_number=10)

    index = build_position_index([func_binding, import_binding])

    # Before import: should resolve to function
    result = resolve_name(index, "sqrt", 5, make_module_scope())
    assert result == func_binding

    # After import: should resolve to import
    result = resolve_name(index, "sqrt", 15, make_module_scope())
    assert result == import_binding


def test_build_index_variable_reassignment() -> None:
    """Multiple assignments to same variable should be tracked."""
    class1_binding = make_class_binding("Calculator")
    class2_binding = make_class_binding("AdvancedCalculator", line_number=5)

    # First assignment to calc variable
    var1_binding = make_variable_binding("calc", line_number=10)

    # Second assignment to calc variable (reassignment)
    var2_binding = make_variable_binding("calc", line_number=20)

    index = build_position_index(
        [class1_binding, class2_binding, var1_binding, var2_binding],
        [(var1_binding, "Calculator"), (var2_binding, "AdvancedCalculator")],
    )

    # At line 15: should resolve to first assignment
    result = resolve_name(index, "calc", 15, make_module_scope())
    assert result is not None
    assert result.line_number == 10
    assert result.target_class == make_qualified_name("__module__.Calculator")

    # At line 25: should resolve to second assignment
    result = resolve_name(index, "calc", 25, make_module_scope())
    assert result is not None
    assert result.line_number == 20
    assert result.target_class == make_qualified_name("__module__.AdvancedCalculator")


def test_build_index_multiple_shadows_in_scope() -> None:
    """Multiple shadowing events for the same name (issue #31)."""
    # from math import sqrt (line 1)
    import1 = make_import_binding("sqrt", "math")

    # def sqrt(): ... (line 10)
    func = make_function_binding("sqrt", line_number=10)

    # from numpy import sqrt (line 20)
    import2 = make_import_binding("sqrt", "numpy", line_number=20)

    index = build_position_index([import1, func, import2])

    # Line 5: should resolve to math.sqrt
    result = resolve_name(index, "sqrt", 5, make_module_scope())
    assert result == import1

    # Line 15: should resolve to local function
    result = resolve_name(index, "sqrt", 15, make_module_scope())
    assert result == func

    # Line 25: should resolve to numpy.sqrt
    result = resolve_name(index, "sqrt", 25, make_module_scope())
    assert result == import2


def test_build_index_class_shadows_import() -> None:
    """Class definition shadows import (issue #31 scenario)."""
    # Import: from external import Calculator
    import_binding = make_import_binding("Calculator", "external")

    # Class: class Calculator: ...
    class_binding = make_class_binding("Calculator", line_number=10)

    index = build_position_index([import_binding, class_binding])

    # Before class: resolves to import
    result = resolve_name(index, "Calculator", 5, make_module_scope())
    assert result == import_binding

    # After class: resolves to local class
    result = resolve_name(index, "Calculator", 15, make_module_scope())
    assert result == class_binding


def test_build_index_variables_in_nested_scope() -> None:
    """Variable resolution works in nested scopes."""
    func_scope = make_function_scope("process")

    # class Calculator at module level
    class_binding = make_class_binding("Calculator")

    # calc = Calculator() inside function
    var_binding = make_variable_binding(
        "calc",
        line_number=10,
        scope_stack=func_scope,
        qualified_name=make_qualified_name("__module__.process.calc"),
    )

    index = build_position_index([class_binding, var_binding], [(var_binding, "Calculator")])

    # Variable in function scope should resolve to module-level class
    result = resolve_name(index, "calc", 15, func_scope)
    assert result is not None
    assert result.target_class == make_qualified_name("__module__.Calculator")


def test_build_index_with_no_unresolved_variables() -> None:
    """Index building works when unresolved_variables is None."""
    binding = make_function_binding("foo")

    # Call with unresolved_variables=None (default)
    index = build_position_index([binding])

    result = resolve_name(index, "foo", 10, make_module_scope())
    assert result == binding


def test_build_index_with_empty_unresolved_list() -> None:
    """Index building works when unresolved_variables is empty list."""
    binding = make_function_binding("foo")

    # Call with empty list
    index = build_position_index([binding], [])

    result = resolve_name(index, "foo", 10, make_module_scope())
    assert result == binding
